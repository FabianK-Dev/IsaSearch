/*  Title:      IsaSearch/isabelle/src/tests.scala

Component checks and cross-language compatibility tests.
*/

package isabelle.isasearch


import isabelle._

import isabelle.find_facts.Solr
import org.apache.lucene.index.DirectoryReader
import org.apache.lucene.search.{IndexSearcher, KnnFloatVectorQuery}
import org.apache.lucene.store.FSDirectory


object Tests {
  // Frozen reference outputs: the original implementation's, kept as regression tests.
  def goldens: Path = Data.component + Path.explode("tests/goldens.json")

  // Interchange directories in sources are imported, searched, packaged, and corrupted.
  def run(sources: List[String]): Unit = {
    import Data._


    /* portable data and compatibility algorithms */

    assert(Data.distance(Array(1f, 2f), Array(2f, 4f), Distance_Metric.Squared_Euclidean) == 5.0)
    assert(math.abs(Data.distance(Array(1f, 2f), Array(2f, 4f), Distance_Metric.Cosine)) < 1e-12)
    assert(Data.floats(Data.bytes(Array(1f, -2f))).toList == List(1f, -2f))
    assert(Data.template("{{x}} {q}", Map("q" -> "{untouched}")) == "{x} {untouched}")
    assert(Duplicates.sequence_ratio("abcd", "bcde") == 0.75)
    assert(Benchmark.csv("ID,query\r\na,\"hello,\nworld\"\r\n").head("query") == "hello,\nworld")


    /* default configuration */

    {
      val options = Options.init(prefs = "")
      val shipped = Config.default(options)
      assert(shipped.base == (component + Path.explode("etc")).absolute)
      val command = Llama_Server.command(shipped, Llama_Server.Role.Embedding, 8080)
      assert(command.containsSlice(List("-hf", "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0")))
      // Query expansion is shipped disabled: one switch turns on the server's model locally.
      assert(Llama_Server.roles(shipped) == List(Llama_Server.Role.Embedding))
      assert(!new Inference.Client(shipped).configured(Model_Role.Query))
      val expanding = shipped.updated(Llama_Server.Role.Query.key,
        object_at(shipped.values, Llama_Server.Role.Query.key).updated("enabled", true))
      val query = Llama_Server.command(expanding, Llama_Server.Role.Query, 8081)
      assert(query.containsSlice(List("--alias", "gemma-4-26B-A4B-it-qat")) &&
        query.contains("--no-mmproj") && !query.contains("--embedding"))
      using(new Llama_Server.Servers(expanding)) { servers =>
        assert(new Inference.Client(servers.config).configured(Model_Role.Query))
        assert(servers.waiting(Llama_Server.Role.Query), "Servers start on first use")
      }
      assert(Config.default(options.string.update("isasearch_config", "")).values.isEmpty)
      var rejected = false
      try { Config.default(options.string.update("isasearch_config", "$ISASEARCH_HOME/missing")) }
      catch { case ERROR(_) => rejected = true }
      assert(rejected, "Missing default configuration")
    }


    /* golden outputs */

    {
      val golden = read(goldens)
      for (item <- list(golden("similarity")).map(obj)) {
        val got = Duplicates.sequence_ratio(str(item, "a"), str(item, "b"))
        assert(
          math.abs(got - num(item, "ratio", 0)) < 1e-12,
          "SequenceMatcher parity: " + JSON.Format(item)
        )
      }
      val paper = Benchmark.paper_queries()
      assert(paper.provenance == object_at(golden, "paper_provenance"))
      for (item <- list(golden("paper_queries")).map(obj)) {
        val row = object_at(item, "row").map { case (k, v) => k -> v.toString }
        assert(paper.for_row(row) == object_at(item, "expected"), "Paper query parity: " + row("ID"))
      }
      val index = Map("baselines" -> Map("UR" -> Map(
        "result_file" -> "bad.json", "results_sha256" -> "wrong")))
      var rejected = false
      try {
        Benchmark.paper_queries(name =>
          Bytes(if (name.endsWith("paper-baselines.json")) JSON.Format(index) else "{}"))
      }
      catch { case ERROR(_) => rejected = true }
      assert(rejected, "Reject paper inputs with a mismatched checksum")
      for (item <- list(golden("reports")).map(obj); exact <- List(false, true)) {
        val got = Duplicate_Report.render(object_at(item, "report"), near_exact_only = exact)
        val expected = str(item, if (exact) "near_exact" else "possible")
        assert(got == expected, "Duplicate report parity:\n" + got + "\nExpected:\n" + expected)
      }
      for (item <- list(golden("metrics")).map(obj)) {
        val got = Benchmark.metrics(list(item("results")).map(obj), list(item("targets")).map(obj))
        object_at(item, "expected").foreach { case (k, v) =>
          assert(math.abs(number(got(k)) - number(v)) < 1e-12, "Metric parity: " + k)
        }
      }
      for (item <- list(golden("normalized")).map(obj))
        assert(Text_Preparation.statement(str(item, "input")) == str(item, "expected"))
      for (item <- list(golden("verdicts")).map(obj)) {
        val (value, reason) = Duplicates.verdict(str(item, "input"))
        assert(List(value.name, reason) == list(item("expected")))
      }
      for (item <- list(golden("classifications")).map(obj))
        assert(
          Duplicates
            .classify(object_at(item, "candidate"), Config(Map.empty))
            .map(_.name)
            .getOrElse("") == str(item, "tier")
        )
      for (item <- list(golden("comparisons")).map(obj)) {
        def results(name: String): Obj =
          if (item.contains(name)) object_at(item, name)
          else Benchmark_Comparison.load(component + Path.explode(str(item, name + "_file")))
        val got = Benchmark_Comparison.report(results("previous"), results("current"))
        assert(got == str(item, "report"), "Comparison parity:\n" + got)
      }
    }


    /* AFP entry metadata */

    Isabelle_System.with_tmp_dir("isasearch-afp") { afp =>
      val entries = Isabelle_System.make_directory(afp + Path.explode("metadata/entries"))
      File.write(entries + Path.basic("CoreC++.toml"), "title = \"Core C++\"\n")
      assert(str(Corpus_Build.metadata(afp, "CoreC++"), "title") == "Core C++",
        "AFP entry names beyond index names")
    }


    /* statements and search filters */

    {
      val statement = Text_Preparation.statement(
        "lemma countable_union_of_Union [simp]:\n  \"countable union_of P ⟹ ⋃ A ∈ X\"\nproof -")
      assert(statement == "\"countable union_of P ⟹ ⋃ A ∈ X\"", statement)
      assert(Text_Preparation.mentions(statement, "countable"))
      assert(!Text_Preparation.mentions(statement, "union"), "Whole names only")
      assert(!Text_Preparation.mentions("\"uncountable A\"", "countable"))
      assert(Text_Preparation.mentions("\"Set.countable A\"", "countable"))
      assert(Text_Preparation.mentions(statement, "\\<Union>") &&
        Text_Preparation.mentions(statement, "⋃"))
      assert(!Text_Preparation.mentions(statement, "\\<Inter>"))

      def hit(id: String, entry: String, src: String, session: String = "S"): Obj =
        Map("id" -> id, "entry" -> entry, "src" -> src, "session" -> session)
      val ranked = List(
        hit("a", "Zippy", "lemma set_map [simp]: \"set (map f xs) = f ` set xs\"\nby (rule x)"),
        hit("b", "", "lemma set_map [simp]: \"set (map f xs) = f ` set xs\"\nby (rule x)"),
        hit("c", "E", "lemma other: \"P\""),
        hit("d", "F", "lemma restated:\n  \"set (map f xs) = f ` set xs\" by (rule x)"),
        hit("e", "G", "lemma more: \"Q\""))
      val collapsed = Search.collapse(ranked.iterator, 2)
      assert(collapsed.map(str(_, "id")) == List("b", "c"),
        "Copies as one result, represented by the distribution")
      assert(list(collapsed.head("copies")).map(c => str(obj(c), "id")) == List("a", "d"))
      assert(list(collapsed(1)("copies")).isEmpty)

      assert(Search.qualifier(Map("theory" -> "Groebner_Bases.Reduced_GB",
        "thms" -> List("Reduced_GB.gd_term.is_reduced_GB_unique"))).contains("gd_term"))
      assert(Search.qualifier(Map("theory" -> "HOL.List",
        "thms" -> List("List.set_map"))).isEmpty)
      assert(Search.qualifier(Map("theory" -> "Regular-Sets.Pi", "thms" -> Nil,
        "consts" -> List("Pi.embed.rderiv"))).contains("embed"))
      assert(Search.qualifier(Map("theory" -> "Regular-Sets.Derivatives",
        "thms" -> List("Derivatives.deriv_graph.intros(1)", "Derivatives.deriv.simps(1)"),
        "consts" -> List("Derivatives.deriv_graph", "Derivatives.deriv"))).isEmpty,
        "Generated facts are qualified by their constant")

      val filter = Search_Filter(Search_Source.All, Some(Set("E", "F")), Some(Set("S")),
        List("countable", "⋃"))
      assert(Search.filter(Search.filter_parameters(filter).toMap) == filter)
      assert(Search.filter(Map.empty) == Search_Filter())
      assert(filter.admits(hit("x", "E", "lemma x: \"countable (⋃ A)\"")))
      assert(!filter.admits(hit("x", "E", "lemma x: \"countable (⋃ A)\"", session = "T")))
      assert(!filter.admits(hit("x", "E", "lemma countable: \"⋃ A\"")),
        "Mentions in the statement, not in the name")
      for (bad <- List(Map("source" -> "distribution", "entries" -> "E"),
          Map("source" -> "nowhere"))) {
        val rejected =
          try { Search.filter(bad); false }
          catch { case _: Search.Bad_Request => true }
        assert(rejected, "Rejected filter: " + bad)
      }
    }


    /* prefilter by source and AFP entry */

    Isabelle_System.with_tmp_dir("isasearch-prefilter") { tmp =>
      val schema = new Index.Schema(2, Distance_Metric.Cosine)
      val docs = List("d0" -> "", "d1" -> "E", "d2" -> "F", "d3" -> "", "d4" -> "E")
      using(Solr.init(tmp + Path.basic("solr")).init_database("theorems", schema)) { db =>
        db.transaction {
          db.execute_batch_insert(docs.zipWithIndex.map { case ((id, entry), i) =>
            (doc: Solr.Document) => {
              doc.string(schema.id) = id
              doc.string(schema.entry) = entry
              doc.string(schema.record) = JSON.Format(Map("id" -> id, "entry" -> entry))
              doc.double(schema.vector) = List(math.cos(i * 0.1), math.sin(i * 0.1))
            }
          })
        }
      }
      val spec = Index.Spec(Map("kind" -> "theorems", "dimension" -> 2, "count" -> docs.size,
        "metric" -> "cosine", "recipe" -> Map("model" -> "m", "add_metadata" -> false,
          "prompts" -> Map("embed" -> "e", "retrieve" -> "r"))))
      using(new Index.Corpus(tmp, spec)) { corpus =>
        def ids(filter: Search_Filter, exclude: String = ""): List[String] =
          corpus.ranked(Array(1f, 0f), 10, filter, exclude).map(str(_, "id")).toList
        assert(ids(Search_Filter()) == List("d0", "d1", "d2", "d3", "d4"))
        assert(ids(Search_Filter(Search_Source.Distribution)) == List("d0", "d3"))
        assert(ids(Search_Filter(Search_Source.AFP)) == List("d1", "d2", "d4"))
        assert(ids(Search_Filter(entries = Some(Set("E")))) == List("d0", "d1", "d3", "d4"))
        assert(ids(Search_Filter(Search_Source.AFP, Some(Set("F")))) == List("d2"))
        assert(ids(Search_Filter(Search_Source.AFP, Some(Set.empty))).isEmpty)
        assert(ids(Search_Filter(Search_Source.AFP), exclude = "E") == List("d2"))
      }
    }


    /* segment merging */

    Isabelle_System.with_tmp_dir("isasearch-merge") { tmp =>
      val schema = new Index.Schema(2, Distance_Metric.Cosine)
      // More commits than a tier of Lucene's default merge policy holds.
      val vectors = (0 until 12).toList.map { i =>
        val angle = i * math.Pi / 22
        Array(math.cos(angle).toFloat, math.sin(angle).toFloat)
      }
      using(Solr.init(tmp + Path.basic("solr")).init_database("theorems", schema)) { db =>
        for ((vector, i) <- vectors.zipWithIndex) db.transaction {
          db.execute_batch_insert(List((doc: Solr.Document) => {
            doc.string(schema.id) = "d" + i
            doc.string(schema.entry) = "E"
            doc.string(schema.record) = "{}"
            doc.double(schema.vector) = vector.toList.map(_.toDouble)
          }))
        }
      }
      val index = Index.lucene_index(tmp, Corpus_Kind.Theorems)
      def segments_nearest(): (Int, String) =
        using(FSDirectory.open(index.java_path).nn) { dir =>
          using(DirectoryReader.open(dir).nn) { reader =>
            val query = new KnnFloatVectorQuery("vector", vectors(4), 1)
            val hit = new IndexSearcher(reader).search(query, 1).nn.scoreDocs.nn(0).nn
            (reader.leaves().nn.size, reader.storedFields().nn.document(hit.doc).nn.get("id").nn)
          }
        }
      assert(segments_nearest() == (12, "d4"), "Solr leaves the committed segments unmerged")
      Index.merge_segments(index)
      assert(segments_nearest() == (1, "d4"), "Segments merged into one, vectors retained")
    }


    /* index import, readers, packaging, and failed imports */

    for ((source, n) <- sources.zipWithIndex) {
      val name = "test-" + n + "-" + UUID.random_string()
      val root = Index.import_index(Path.explode(source), name)
      using(new Index.Snapshot(root)) { snapshot =>
        using(new Index.Snapshot(root)) { second =>
          for ((kind, corpus) <- snapshot.corpora) {
            assert(corpus.segments == 1, "Imported corpus merged into one segment")
            val input = Path.explode(source) + Path.basic(kind.name)
            val source_vectors =
              Data.floats(Bytes.read(input + Path.basic(Index_Format.vectors)).make_array)
                .grouped(corpus.spec.dimension).map(_.toList)
            for ((line, vector) <- split_lines(File.read(input + Path.basic(Index_Format.documents)))
                .filter(_.nonEmpty).zip(source_vectors))
              assert(
                corpus.vector(corpus.get(str(obj(JSON.parse(line)), "id")).get._1).toList == vector,
                "Vectors read back exactly as imported"
              )
            val docs = corpus.all.toList
            assert(docs.size == corpus.spec.count)
            for ((id, doc) <- docs) {
              val vector = corpus.vector(id)
              val hits = corpus.search(vector, corpus.spec.count, 1)
              val own = hits.find(h => str(h, "id") == str(doc, "id")).get
              assert(num(own, "distance", 1) < 1e-6, "Self retrieval")
              assert(second(kind).get(str(doc, "id")).nonEmpty, "Concurrent read-only snapshot")
              val exact = docs.map { case (j, d) =>
                str(d, "id") -> distance(vector, corpus.vector(j), corpus.spec.metric)
              }.toMap
              hits.foreach(h =>
                assert(math.abs(num(h, "distance", 0) - exact(str(h, "id"))) < 1e-6)
              )
              assert(
                corpus.search(vector, 2, corpus.spec.count) == hits.take(2),
                "Limit applied after exact ranking of all candidates"
              )
              assert(
                corpus
                  .search(vector, corpus.spec.count, 1, str(doc, "entry"))
                  .forall(h => str(h, "entry") != str(doc, "entry"))
              )
            }
          }
        }
      }
      Isabelle_System.with_tmp_dir("isasearch-package") { target =>
        val packaged = Index.package_index(name, target)
        val extracted = Isabelle_System.make_directory(target + Path.basic("relocated"))
        File_Store.database_extract(
          packaged + Path.basic(name).db,
          extracted,
          compress_cache = Compress.Cache.make()
        )
        using(new Index.Snapshot(extracted)) { s => assert(s.corpora.nonEmpty) }
      }
      val before = read(Index.location(name) + Path.basic("current.json"))
      Isabelle_System.with_tmp_dir("isasearch-corrupt") { bad =>
        write(
          bad + Path.basic(Index_Format.manifest),
          read(Path.explode(source) + Path.basic(Index_Format.manifest))
        )
        var failed = false
        try { Index.import_index(bad, name) }
        catch { case scala.util.control.NonFatal(_) => failed = true }
        assert(failed, "Corrupt import must fail")
        assert(
          read(Index.location(name) + Path.basic("current.json")) == before,
          "Failed import changed active index"
        )
      }
      Isabelle_System.rm_tree(Index.location(name))
    }
    Output.writeln("IsaSearch tests passed")
  }
}
