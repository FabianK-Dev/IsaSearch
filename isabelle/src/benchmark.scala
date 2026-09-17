/*  Title:      IsaSearch/isabelle/src/benchmark.scala

Benchmark execution with the paper's saved query inputs and Python-compatible scoring.
*/

package isabelle.isasearch


import isabelle._


object Benchmark {
  import Data._


  /** benchmark defaults **/

  private val hit_cutoff = 10
  val query_types = List("Title query", "Natural language query", "Noisy natural language query")

  private def resource(name: String): Bytes = {
    val stream = Option(getClass.getResourceAsStream("/benchmark/" + name))
      .getOrElse(error("Missing bundled benchmark resource: " + name))
    using(stream)(Bytes.read_stream(_))
  }

  def default_csv: Path = {
    val path = home + Path.explode("benchmark/benchmark.csv")
    val content = resource("benchmark.csv")
    Isabelle_System.make_directory(path.dir)
    if (!path.is_file || Bytes.read(path) != content) Bytes.write(path, content)
    path
  }


  /** saved paper queries (benchmark/queries.py) **/

  case class Paper_Queries(queries: Map[String, Obj], provenance: Obj) {
    def for_row(row: Map[String, String]): Map[String, Obj] =
      queries.get(row("ID")) match {
        case Some(reference) => query_types.map { kind =>
          val input = object_at(reference, kind)
          kind -> Map("query" -> input("query"), "source" -> input.getOrElse("source", null))
        }.toMap
        case None => query_types.take(2).map { kind =>
          kind -> Map(
            "query" -> row.getOrElse(kind, ""),
            "source" -> row.getOrElse("Natural language query source", null)
          )
        }.toMap
      }
  }

  def paper_queries(load: String => Bytes = resource): Paper_Queries = {
    val index = JSON.Object.parse(load("results/paper-baselines.json").text)
    val baseline = object_at(object_at(index, "baselines"), "UR")
    val filename = str(baseline, "result_file")
    val content = load("results/" + filename)
    val digest = hash(content.make_array)
    if (digest != str(baseline, "results_sha256"))
      error("Paper query source '" + filename + "' does not match its recorded SHA-256")
    val results = JSON.Object.parse(content.text)
    val queries = results.toList.collect {
      case (target, value) if target != "summary" && !bool(object_at(obj(value), "metadata"), "skipped") =>
        val reference = object_at(obj(value), "queries")
        query_types.foreach { kind =>
          if (JSON.string(object_at(reference, kind), "query").isEmpty)
            error("Paper query source lacks text for '" + kind + "' in '" + target + "'")
        }
        target -> reference
    }.toMap
    Paper_Queries(queries, Map(
      "mode" -> "replay_paper_queries",
      "reference_strategy" -> "UR",
      "reference_result" -> filename,
      "reference_sha256" -> digest,
      "available_targets" -> queries.size,
      "available_queries" -> (queries.size * query_types.size),
      "extra_target_input_policy" -> "csv_title_and_natural_language",
      "missing_noisy_query_policy" -> "skip_query"
    ))
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
    val paper = paper_queries()
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
        val started_at = java.time.Instant.now().toString
        var results = Map.empty[String, JSON.T]
        val timings = scala.collection.mutable.ListBuffer.empty[Obj]
        for (row <- rows) {
          val id = row.getOrElse("ID", error("Missing benchmark ID column"))
          var reason = ""
          if (row.getOrElse("Skip", "") == "true")
            reason = "Annotation: " + row.getOrElse("Annotation", "")
          val targetText = row.getOrElse("Target Identifier", "")
          var targets = List.empty[Obj]
          var metadata = Map.empty[String, JSON.T]
          if (reason.isEmpty && targetText.isEmpty) reason = "target_identifier_missing"
          if (reason.isEmpty) try { targets = list(JSON.parse(targetText)).map(obj).distinct }
          catch { case ERROR(_) => reason = "target_identifier_parse_error" }
          if (reason.isEmpty) metadata += "target_identifier" -> targets
          if (reason.isEmpty && !docs.exists(correct(_, targets)))
            reason = "target_document_not_found"
          if (reason.nonEmpty)
            results += id -> Map(
              "metadata" -> (metadata ++ Map("skipped" -> true, "skipped_reason" -> reason)),
              "queries" -> Map.empty[String, JSON.T]
            )
          else {
            var queries = Map.empty[String, JSON.T]
            val inputs = paper.for_row(row)
            for (kind <- query_types) {
              if (!inputs.contains(kind))
                metadata += "skipped_queries" -> Map(kind -> "paper_noisy_query_missing")
              else {
                val input = inputs(kind)
                val query = str(input, "query")
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
                    "source" -> input("source"),
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
            }
            results += id -> Map("metadata" -> metadata, "queries" -> queries)
          }
        }
        val strategy_dir = Isabelle_System.make_directory(run_dir + Path.basic(strategy.name))
        val result_path = strategy_dir + Path.basic("results.json")
        write(result_path, results.updated("summary", summary(results)))
        write(
          strategy_dir + Path.basic("manifest.json"),
          Map(
            "strategy" -> strategy.name,
            "index" -> name,
            "index_manifest_sha256" -> file_hash(
              engine.snapshot.root + Path.basic(Index_Format.manifest)
            ),
            "dataset_sha256" -> file_hash(data),
            "started_at" -> started_at,
            "finished_at" -> java.time.Instant.now().toString,
            "query_inputs" -> paper.provenance,
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
