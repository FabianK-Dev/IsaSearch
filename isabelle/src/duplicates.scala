/*  Title:      IsaSearch/isabelle/src/duplicates.scala

Duplicate scoring, AFP entry analysis, and reports.
*/

package isabelle.isasearch


import isabelle._


object Duplicates {
  import Data._
  import Text_Preparation.strip_proof


  /** scoring settings **/

  val tiers = Duplicate_Tier.values.toList
  val verdicts = Verdict.values.toList
  private val min_statement_length = 8
  private val ground_truth_threshold = 0.85
  private val max_ground_truth_group = 50
  private val self_failure_limit = 0.05
  private val self_search_extra = 301

  case class Settings(config: Config) {
    val top_k = config.positive("dedup_top_k", 10)
    val distance = config.number("dedup_distance_threshold", 0.3)
    val strong_distance = config.number("dedup_strong_distance_threshold", 0.05)
    val syntactic = config.number("dedup_syntactic_threshold", 0.9)
    val max_judged = config.integer("dedup_max_judged_per_item", 3)
    val excerpt_length = config.positive("theorem_max_length", 3000)

    def json: Obj = Map(
      "top_k" -> top_k,
      "distance" -> distance,
      "strong_distance" -> strong_distance,
      "syntactic" -> syntactic
    )
  }


  /** syntactic similarity **/

  private lazy val commands = str(read(component + Path.explode("etc/scoring.json")), "commands")

  def normalized(s: String): String = strip_proof(s)
    .replaceFirst("^\\s*(?:" + commands + ")\\b", " ")
    .replaceFirst("^\\s*[A-Za-z_][A-Za-z0-9_'.]*\\s*(?:\\[[^\\]]*\\])?\\s*:(?!:)", " ")
    .replaceAll("(?U)\\s+", " ")
    .trim

  // difflib.SequenceMatcher(None, a, b), including its default autojunk heuristic.
  def sequence_ratio(a0: String, b0: String): Double = {
    val a = a0.codePoints().toArray
    val b = b0.codePoints().toArray
    if (a.length + b.length == 0) return 1.0
    val positions = b.indices
      .groupBy(b(_))
      .view
      .mapValues(_.toList)
      .toMap
      .filterNot { case (_, js) => b.length >= 200 && js.size > b.length / 100 + 1 }

    def longest(alo: Int, ahi: Int, blo: Int, bhi: Int): (Int, Int, Int) = {
      var ai = alo
      var bj = blo
      var size = 0
      var previous = Map.empty[Int, Int]
      for (i <- alo until ahi) {
        val current = scala.collection.mutable.Map.empty[Int, Int]
        for (j <- positions.getOrElse(a(i), Nil) if j >= blo && j < bhi) {
          val k = previous.getOrElse(j - 1, 0) + 1
          current(j) = k
          if (k > size) {
            ai = i - k + 1
            bj = j - k + 1
            size = k
          }
        }
        previous = current.toMap
      }
      while (ai > alo && bj > blo && a(ai - 1) == b(bj - 1)) {
        ai -= 1
        bj -= 1
        size += 1
      }
      while (ai + size < ahi && bj + size < bhi && a(ai + size) == b(bj + size)) size += 1
      (ai, bj, size)
    }

    var pending = List((0, a.length, 0, b.length))
    var matches = 0
    while (pending.nonEmpty) {
      val (alo, ahi, blo, bhi) = pending.head
      pending = pending.tail
      val (i, j, k) = longest(alo, ahi, blo, bhi)
      if (k > 0) {
        matches += k
        if (alo < i && blo < j) pending = (alo, i, blo, j) :: pending
        if (i + k < ahi && j + k < bhi) pending = (i + k, ahi, j + k, bhi) :: pending
      }
    }
    2.0 * matches / (a.length + b.length)
  }

  def similarity(a: String, b: String): Double = {
    val x = normalized(a)
    val y = normalized(b)
    if (x.codePointCount(0, x.length) < min_statement_length ||
        y.codePointCount(0, y.length) < min_statement_length) 0.0
    else sequence_ratio(x, y)
  }


  /** evidence classification **/

  def classify(candidate: Obj, config: Config): Option[Duplicate_Tier] = {
    val settings = Settings(config)
    if (
      num(candidate, "distance", Double.PositiveInfinity) <= settings.strong_distance ||
      num(candidate, "syntactic_similarity", 0) >= settings.syntactic
    ) Some(Duplicate_Tier.Near_Exact)
    else if (str(candidate, "verdict") == Verdict.Duplicate.name) Some(Duplicate_Tier.Likely)
    else if (num(candidate, "distance", Double.PositiveInfinity) <= settings.distance)
      Some(Duplicate_Tier.Possible)
    else None
  }

  def verdict(raw: String): (Verdict, String) = {
    val text = marked(raw)
    "VERDICT\\s*:\\s*([A-Za-z]+)".r.findFirstMatchIn(text) match {
      case Some(m) =>
        val value = verdicts
          .filterNot(_ == Verdict.Unknown)
          .find(_.name == m.group(1).toUpperCase(java.util.Locale.ROOT))
        (
          value.getOrElse(Verdict.Unknown),
          truncate(if (value.isDefined) text.substring(m.end).trim else text, 300)
        )
      case _ => (Verdict.Unknown, truncate(text, 300))
    }
  }


  /** synthetic ground truth **/

  def ground_truth(docs: List[Obj], relevant: Set[String]): (Map[String, Set[String]], Int) = {
    val groups = scala.collection.mutable.Map.empty[String, List[Obj]]
    docs.filter(d => str(d, "entry", entry(str(d, "id"))).nonEmpty).foreach { d =>
      (strings(d, "consts") ::: strings(d, "typs"))
        .map(_.split('.').last)
        .filter(_.nonEmpty)
        .distinct
        .foreach { name =>
          groups(name) = groups.getOrElse(name, Nil) :+ d
        }
    }
    val result = scala.collection.mutable.Map.empty[String, Set[String]]
    var skipped = 0
    groups.values.foreach { group =>
      if (group.size > max_ground_truth_group) skipped += 1
      else if (group.exists(d => relevant(str(d, "id")))) {
        for (i <- group.indices; j <- i + 1 until group.size) {
          val a = group(i)
          val b = group(j)
          val x = str(a, "id")
          val y = str(b, "id")
          if (
            (relevant(x) || relevant(y)) && str(a, "entry", entry(x)) != str(
              b,
              "entry",
              entry(y)
            ) && similarity(
              str(a, "src"),
              str(b, "src")
            ) >= ground_truth_threshold
          ) {
            result(x) = result.getOrElse(x, Set.empty) + y
            result(y) = result.getOrElse(y, Set.empty) + x
          }
        }
      }
    }
    (result.toMap, skipped)
  }


  /** entry analysis and reports **/

  def run(
    engine: Search.Engine,
    entries: List[String],
    newest: Int,
    kinds: List[Corpus_Kind],
    cross: Boolean,
    judge: Boolean,
    all_candidates: Boolean,
    out: Path
  ): Path = {
    val config = engine.config
    val settings = Settings(config)
    engine.ready(false)
    val can_judge = judge && bool(engine.capabilities, "query_expansion")
    if (judge && !can_judge)
      Output.warning("LLM judge unavailable; reporting vector and syntactic evidence only")
    val targets = if (cross) Index.kinds else kinds
    targets.foreach(engine.snapshot(_))
    if (cross) {
      val specs = targets.map(engine.snapshot(_).spec)
      if (
        specs
          .map(s =>
            (
              s.dimension,
              s.metric,
              str(s.recipe, "model"),
              str(s.prompts, Prompt.Embed),
              s.space.max_characters
            )
          )
          .distinct
          .size != 1
      )
        error("Cross-kind matching requires the same embedding space, metric and embed prompt")
    }
    val indexes = targets.map(k => k -> engine.snapshot(k).all.map(_._2).toList).toMap
    val dates = indexes.valuesIterator.flatten
      .filter(d => str(d, "entry").nonEmpty)
      .map(d => str(d, "entry") -> str(d, "entry_date"))
      .toMap
    val selected =
      if (entries.nonEmpty) entries.distinct
      else
        dates.toList
          .filter(_._2.nonEmpty)
          .sortBy { case (e, d) => (d, e) }
          .reverse
          .take(newest)
          .map(_._1)
    if (selected.isEmpty) error("No entries selected; supply -e ENTRY or import entry dates")
    selected.foreach(e => if (!dates.contains(e)) error("Entry not present in index: " + e))
    val sections = kinds.map { kind =>
      val corpus = engine.snapshot(kind)
      val query_docs =
        indexes(kind).filter(d => selected.contains(str(d, "entry"))).sortBy(d => str(d, "id"))
      val analyses = query_docs.map { doc =>
        val id = str(doc, "id")
        val e = str(doc, "entry")
        val vector = engine.inference.embed(List(str(doc, "embedding_input")), corpus.spec).head
        val self_hits =
          corpus.search(vector, math.min(corpus.spec.count, settings.top_k + self_search_extra))
        val self_pos = self_hits.indexWhere(r => str(r, "id") == id)
        val candidates = (if (cross) targets else List(kind))
          .flatMap { target =>
            engine.snapshot(target).search(vector, settings.top_k, exclude = e)
          }
          .sortBy(d => (num(d, "distance", 0), str(d, "id")))
          .take(settings.top_k)
          .zipWithIndex
          .map { case (candidate, n) =>
            var c = candidate
              .removed("embedding_input")
              .removed("description_artifact")
              .updated("syntactic_similarity", similarity(str(doc, "src"), str(candidate, "src")))
            if (
              can_judge && n < settings.max_judged && num(c, "distance", 1) <= settings.distance
            ) {
              val prompt = template(
                Index.prompt(corpus.spec, Prompt.Judge),
                Map(
                  "item_a" -> truncate(strip_proof(str(doc, "src")), settings.excerpt_length).trim,
                  "item_b" -> truncate(strip_proof(str(c, "src")), settings.excerpt_length).trim
                )
              )
              val (v, reason) = verdict(engine.inference.generate(prompt).text)
              c = c ++ Map("verdict" -> v.name, "justification" -> reason)
            }
            c.updated("tier", classify(c, config).map(_.name).orNull)
          }
        val best =
          tiers.find(t => candidates.exists(c => str(c, "tier") == t.name)).map(_.name).orNull
        doc.removed("embedding_input").removed("description_artifact") ++ Map(
          "best_tier" -> best,
          "self_rank" -> (if (self_pos < 0) null else self_pos + 1),
          "self_distance" -> (if (self_pos < 0) null else self_hits(self_pos)("distance")),
          "candidates" -> candidates
        )
      }
      val (truth, skipped) = ground_truth(indexes(kind), query_docs.map(d => str(d, "id")).toSet)
      val with_truth = analyses.filter(a => truth.getOrElse(str(a, "id"), Set.empty).nonEmpty)
      val recovered = with_truth.count(a =>
        list(a("candidates")).map(obj).exists(c => truth(str(a, "id"))(str(c, "id")))
      )
      val failures = analyses.filter { a =>
        a("self_rank") == null ||
        (number(a("self_rank")) != 1 && number(a("self_distance")) > settings.strong_distance)
      }
      val distances = analyses.flatMap(a => Option(a("self_distance")).map(number))
      val fraction = if (analyses.isEmpty) 0.0 else failures.size.toDouble / analyses.size
      if (fraction > self_failure_limit)
        Output.warning("Self-retrieval failure rate exceeds " + self_failure_limit + " for " + kind)
      val tier_counts =
        (tiers.map(_.name) :+ "none")
          .map(t => t -> analyses.count(a => str(a, "best_tier", "none") == t))
          .toMap
      val cs = analyses.flatMap(a => list(a("candidates")).map(obj))
      val histogram = scala.collection.mutable.LinkedHashMap[String, Int](
        "<= 0.05" -> 0,
        "<= 0.1" -> 0,
        "<= 0.2" -> 0,
        "<= 0.3" -> 0,
        "<= 0.5" -> 0,
        "<= 1.0" -> 0,
        "> 1.0" -> 0
      )
      analyses.foreach(a =>
        list(a("candidates")).headOption.map(obj).foreach { c =>
          val bucket = List(0.05, 0.1, 0.2, 0.3, 0.5, 1.0)
            .find(num(c, "distance", 0) <= _)
            .map(x => "<= " + x)
            .getOrElse("> 1.0")
          histogram(bucket) += 1
        }
      )
      val overlapping = cs
        .filter(c => str(c, "tier").nonEmpty && str(c, "entry").nonEmpty)
        .groupBy(c => str(c, "entry"))
        .toList
        .map { case (e, items) => e -> items.size }
        .sortBy(-_._2)
        .take(20)
        .toMap
      kind.name -> Map[String, JSON.T](
        "entries" -> selected.map { e =>
          val local = analyses.filter(a => str(a, "entry") == e)
          val reported =
            local.filter(a => all_candidates || str(a, "best_tier").nonEmpty).map { a =>
              a.updated("src", truncate(str(a, "src"), 600))
                .updated(
                  "candidates",
                  list(a("candidates"))
                    .map(obj)
                    .filter(c => all_candidates || str(c, "tier").nonEmpty)
                    .map(c => c.updated("src", truncate(str(c, "src"), 600)))
                )
            }
          Map("entry" -> e, "date" -> dates(e), "documents" -> local.size, "items" -> reported)
        },
        "aggregates" -> Map(
          "thresholds" -> settings.json,
          "documents" -> analyses.size,
          "tier_counts" -> tier_counts,
          "documents_with_near_exact_or_likely_duplicate" -> (tier_counts(
            Duplicate_Tier.Near_Exact.name
          ) + tier_counts(Duplicate_Tier.Likely.name)),
          "verdict_counts" -> verdicts
            .map(v => v.name -> cs.count(c => str(c, "verdict") == v.name))
            .toMap,
          "candidate_kind_counts" -> Index.kinds
            .map(k => k.name -> cs.count(c => str(c, "tier").nonEmpty && str(c, "kind") == k.name))
            .toMap,
          "top_1_distance_histogram" -> histogram.toMap,
          "overlapping_entries" -> overlapping
        ),
        "self_retrieval" -> Map(
          "documents" -> analyses.size,
          "self_retrieved" -> (analyses.size - failures.size),
          "failure_fraction" -> fraction,
          "mean_self_distance" -> (if (distances.isEmpty) null else distances.sum / distances.size),
          "failures" -> failures
            .take(20)
            .map(a => a.view.filterKeys(Set("id", "self_rank", "self_distance")).toMap)
        ),
        "synthetic_ground_truth" -> Map(
          "documents_with_known_duplicate" -> with_truth.size,
          "documents_recovered" -> recovered,
          "recall" -> (if (with_truth.isEmpty) null else recovered.toDouble / with_truth.size),
          "skipped_groups" -> skipped
        )
      )
    }.toMap
    val thresholds = settings.json
    val report = Map(
      "generated_at" -> java.time.Instant.now().toString,
      "llm_judge" -> can_judge,
      "cross" -> cross,
      "all_candidates" -> all_candidates,
      "thresholds" -> thresholds,
      "sections" -> sections
    )
    val target =
      Isabelle_System.make_directory(out) + Path.basic("experiment_" + UUID.random_string())
    write(target.ext("json"), report)
    val md = new StringBuilder(
      "# Duplicate analysis of AFP entries\n\nSimilarity is evidence for human review, not a proof of duplication.\n\n"
    )
    md.append("Thresholds: " + JSON.Format(thresholds) + ". LLM judge: " + can_judge + ".\n\n")
    sections.foreach { case (kind, section) =>
      md.append("## " + kind + "\n\n")
      md.append("Self-retrieval: " + JSON.Format(section("self_retrieval")) + "\n\n")
      list(section("entries")).map(obj).foreach { e =>
        md.append("### " + str(e, "entry") + "\n\n")
        list(e("items")).map(obj).foreach { item =>
          md.append("- " + str(item, "id") + " (" + str(item, "best_tier", "unclassified") + ")\n")
          list(item("candidates")).map(obj).foreach { c =>
            md.append(
              "  - " + str(c, "id") + ": distance " + c("distance") + ", syntax " + c(
                "syntactic_similarity"
              ) + ", " + str(c, "tier", "unclassified") + "\n"
            )
          }
        }
        md.append("\n")
      }
    }
    File.write(target.ext("md"), md.toString)
    target.ext("json")
  }
}
