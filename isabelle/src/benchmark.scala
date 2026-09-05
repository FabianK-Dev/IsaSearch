/*  Title:      IsaSearch/isabelle/src/benchmark.scala

Benchmark execution and Python-compatible scoring and query noise.
*/

package isabelle.isasearch


import isabelle._


object Benchmark {
  import Data._
  import Text_Preparation.stopwords


  /** benchmark defaults **/

  val default_seed = 129869
  private val swap_probability = 0.1
  private val character_retention = 0.9
  private val hit_cutoff = 10

  def default_csv: Path = {
    val path = home + Path.explode("benchmark/benchmark.csv")
    val stream = Option(getClass.getResourceAsStream("/benchmark/benchmark.csv"))
      .getOrElse(error("Missing bundled benchmark CSV"))
    val content = using(stream)(Bytes.read_stream(_))
    Isabelle_System.make_directory(path.dir)
    if (!path.is_file || Bytes.read(path) != content) Bytes.write(path, content)
    path
  }


  /** Python-compatible random numbers **/

  // CPython random.Random(integer): MT19937 init_by_array and 53-bit random().

  class Python_Random(seed: Int) {
    private val mt = new Array[Int](624)
    private var pos = 624
    mt(0) = 19650218
    for (i <- 1 until 624) mt(i) = 1812433253 * (mt(i - 1) ^ (mt(i - 1) >>> 30)) + i
    private var i = 1
    for (_ <- 0 until 624) {
      mt(i) = (mt(i) ^ ((mt(i - 1) ^ (mt(i - 1) >>> 30)) * 1664525)) + seed
      i += 1
      if (i >= 624) {
        mt(0) = mt(623)
        i = 1
      }
    }
    for (_ <- 0 until 623) {
      mt(i) = (mt(i) ^ ((mt(i - 1) ^ (mt(i - 1) >>> 30)) * 1566083941)) - i
      i += 1
      if (i >= 624) {
        mt(0) = mt(623)
        i = 1
      }
    }
    mt(0) = 0x80000000

    private def next(): Int = {
      if (pos >= 624) {
        for (k <- 0 until 624) {
          val y = (mt(k) & 0x80000000) | (mt((k + 1) % 624) & 0x7fffffff)
          mt(k) = mt((k + 397) % 624) ^ (y >>> 1) ^ (if ((y & 1) != 0) 0x9908b0df else 0)
        }
        pos = 0
      }
      var y = mt(pos)
      pos += 1
      y ^= y >>> 11
      y ^= (y << 7) & 0x9d2c5680
      y ^= (y << 15) & 0xefc60000
      y ^= y >>> 18
      y
    }

    def random(): Double =
      ((next() >>> 5).toDouble * 67108864.0 + (next() >>> 6)) / 9007199254740992.0
  }


  /** query noise **/

  def noisy(text: String, random: Python_Random): String = {
    val words = text
      .replace("[...]", " ")
      .replaceAll("[\\[\\]\\.,:]", " ")
      .toLowerCase(java.util.Locale.ROOT)
      .split("(?U)\\s+")
      .filter(w => w.nonEmpty && !stopwords(w))
    var i = 0
    while (i < words.length - 1) {
      if (random.random() < swap_probability) {
        val w = words(i)
        words(i) = words(i + 1)
        words(i + 1) = w
        i += 2
      }
      else i += 1
    }
    val out = new StringBuilder
    words
      .mkString(" ")
      .codePoints()
      .toArray
      .foreach(c =>
        if (random.random() < character_retention) out.append(new String(Character.toChars(c)))
      )
    out.toString
  }


  /** benchmark data **/

  def csv(text: String): List[Map[String, String]] = {
    // Isabelle's CSV API prints records; Solr's bundled parser also reads quoted multiline fields.
    val parser = new org.apache.solr.internal.csv.CSVParser(
      new java.io.StringReader(text),
      org.apache.solr.internal.csv.CSVStrategy.EXCEL_STRATEGY
    )
    val rows = Option(parser.getAllValues()).toList.flatMap(_.toList).map(_.toList)
    if (rows.isEmpty) error("Empty benchmark CSV")
    val header = rows.head
    rows.tail
      .filterNot(_ == List(""))
      .map { values =>
        if (values.length != header.length) error("CSV field count differs from header")
        header.zip(values).toMap
      }
      .toList
  }


  /** metrics **/

  def correct(doc: Obj, targets: List[Obj]): Boolean =
    targets.exists(t => t.forall { case (k, v) => doc.get(k).contains(v) })

  def metrics(results: List[Obj], targets: List[Obj]): Obj = {
    val ranks = results.zipWithIndex.collect { case (doc, i) if correct(doc, targets) => i + 1 }

    def dcg(rs: Iterable[Int]): Double =
      rs.iterator.map(r => 1.0 / (math.log(r + 1) / math.log(2))).sum
    val ideal = dcg(1 to targets.size)
    Map(
      "top_k_accuracy" -> (if (ranks.exists(_ <= hit_cutoff)) 1 else 0),
      "normalized_discounted_cumulative_gain" -> (if (ideal == 0) 0.0 else dcg(ranks) / ideal),
      "reciprocal_rank" -> ranks.headOption.map(1.0 / _).getOrElse(0.0),
      "rank" -> ranks.headOption.getOrElse(results.size)
    )
  }

  def summary(results: Obj): Obj = {
    val values =
      scala.collection.mutable.Map.empty[String, scala.collection.mutable.Map[String, List[Double]]]
    results.values.map(obj).filterNot(r => bool(object_at(r, "metadata"), "skipped")).foreach { row =>
      object_at(row, "queries").foreach { case (kind, q) =>
        for (
          group <- List(kind, "all_queries"); (metric, value) <- object_at(obj(q), "metrics")
        ) {
          val bucket = values.getOrElseUpdate(group, scala.collection.mutable.Map.empty)
          bucket(metric) = number(value) :: bucket.getOrElse(metric, Nil)
        }
      }
    }
    Map("all_queries" -> Map.empty[String, JSON.T]) ++ values.map { case (kind, ms) =>
      kind -> ms.map { case (m, vs) =>
        m -> Map("average" -> (vs.sum / vs.size), "sample_size" -> vs.size)
      }.toMap
    }.toMap
  }


  /** strategy execution **/

  val strategies = Benchmark_Strategy.values.toList

  def run(
    config: Config,
    plain_index: String,
    metadata_index: String,
    data: Path,
    requested: List[Benchmark_Strategy],
    out: Path,
    progress: Progress
  ): List[Path] = {
    if (requested.isEmpty || requested.exists(s => !strategies.contains(s)))
      error("Strategies: " + strategies.mkString(","))
    val seed = config.integer("benchmark_seed", default_seed)
    val rows = csv(File.read(data))
    val selected = requested.distinct
    val names = selected.map(s => if (s.metadata) metadata_index else plain_index).distinct
    if (names.exists(_.isEmpty))
      error("Specify both -i INDEX and -m METADATA_INDEX for all six strategies")
    val snapshots = names.map(n => n -> new Index.Snapshot(Index.current(n))).toMap
    try {
      val engines = snapshots.map { case (n, s) => n -> new Search.Engine(s, config) }
      selected.foreach { s =>
        val name = if (s.metadata) metadata_index else plain_index
        val engine = engines(name)
        if (bool(engine.snapshot(Corpus_Kind.Theorems).spec.recipe, "add_metadata") != s.metadata)
          error("Index metadata variant does not match strategy " + s)
        engine.ready(s.mode.expands)
      }
      val run_dir =
        Isabelle_System.make_directory(out + Path.basic("benchmark-" + UUID.random_string()))
      selected.map { strategy =>
        val name = if (strategy.metadata) metadata_index else plain_index
        val engine = engines(name)
        val corpus = engine.snapshot(Corpus_Kind.Theorems)
        val docs = corpus.all.map(_._2).toList
        val random = new Python_Random(seed)
        var results = Map.empty[String, JSON.T]
        val timings = scala.collection.mutable.ListBuffer.empty[Obj]
        for (row <- rows) {
          val id = row.getOrElse("ID", error("Missing benchmark ID column"))
          var reason = ""
          if (row.getOrElse("Skip", "") == "true")
            reason = "Annotation: " + row.getOrElse("Annotation", "")
          val targetText = row.getOrElse("Target Identifier", "")
          var targets = List.empty[Obj]
          if (reason.isEmpty && targetText.isEmpty) reason = "target_identifier_missing"
          if (reason.isEmpty) try { targets = list(JSON.parse(targetText)).map(obj).distinct }
          catch { case ERROR(_) => reason = "target_identifier_parse_error" }
          if (reason.isEmpty && !docs.exists(correct(_, targets)))
            reason = "target_document_not_found"
          if (reason.nonEmpty)
            results += id -> Map(
              "metadata" -> Map("skipped" -> true, "skipped_reason" -> reason),
              "queries" -> Map.empty[String, JSON.T]
            )
          else {
            var queries = Map.empty[String, JSON.T]
            val natural = row.getOrElse("Natural language query", "")
            for (
              kind <- List("Title query", "Natural language query", "Noisy natural language query")
            ) {
              val query =
                if (kind == "Noisy natural language query") noisy(natural, random)
                else row.getOrElse(kind, "")
              if (query.nonEmpty) {
                progress.echo(strategy.name + ": " + id + " / " + kind)
                val response = engine.search(
                  query,
                  mode = strategy.mode
                )
                val found = list(response("results")).map(obj)
                val ms = metrics(found, targets).updated(
                  "duration",
                  math.rint(num(response, "duration", 0) * 10) / 10
                )
                val top =
                  if (!config.boolean("benchmark_add_top_results")) Nil
                  else
                    found.take(hit_cutoff).zipWithIndex.map { case (r, i) =>
                      Map(
                        "rank" -> (i + 1),
                        "distance" -> r("distance"),
                        "id" -> r("id"),
                        "entity_kname" -> r.getOrElse("entity_kname", null),
                        "embedding_string" -> (str(r, "llm_description").trim + "\n\n" + str(
                          r,
                          "src"
                        ).trim)
                      )
                    }
                queries += kind -> Map(
                  "metrics" -> ms,
                  "query" -> query,
                  "source" -> row.getOrElse("Natural language query source", ""),
                  "refined_query" -> response("refined_query"),
                  "top_results" -> top
                )
                timings += Map(
                  "id" -> id,
                  "query_type" -> kind,
                  "elapsed_duration" -> response("elapsed_duration"),
                  "cache_hit" -> response("cache_hit")
                )
              }
            }
            results += id -> Map("metadata" -> Map.empty[String, JSON.T], "queries" -> queries)
          }
        }
        val filename = strategy.name + "_" + str(corpus.spec.recipe, "document_model", "unknown")
          .replaceAll("[^A-Za-z0-9_.-]", "-") + "_" +
          engine.inference.model(Model_Role.Query).replaceAll("[^A-Za-z0-9_.-]", "-")
        val result_path = run_dir + Path.basic(filename + ".json")
        write(result_path, results.updated("summary", summary(results)))
        write(
          run_dir + Path.basic(filename + ".run.json"),
          Map(
            "strategy" -> strategy.name,
            "index" -> name,
            "index_manifest_sha256" -> file_hash(
              engine.snapshot.root + Path.basic(Index_Format.manifest)
            ),
            "dataset_sha256" -> file_hash(data),
            "seed" -> seed,
            "stopwords_sha256" -> file_hash(
              component + Path.explode("benchmark/stopwords_english.txt")
            ),
            "config" -> config.public_values,
            "recipe" -> corpus.spec.recipe,
            "cache_policy" -> config.boolean("enable_llm_output_cache", true),
            "timings" -> timings.toList
          )
        )
        result_path
      }
    }
    finally { snapshots.values.foreach(_.close()) }
  }
}
