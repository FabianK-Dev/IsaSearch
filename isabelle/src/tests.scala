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
    {
      val newest_first = List("20261109-afp-0726d9f1e0bf", "20261108-afp-0726d9f1e0bf",
        "20261101-afp-aaaaaaaaaaaa").map(t => Release.Info("index-plain-" + t, "", Nil))
      def entry(release: String, distance: Int): Obj =
        Map("release" -> release, "distance" -> distance)
      val listing = Map("revisions" -> Map(
        ("c" * 40) -> entry(newest_first(2).tag, 2),
        ("d" * 40) -> entry("index-plain-20260101-afp-dddddddddddd", 0)))
      val covered = Release.covered(newest_first, Some(listing))
      def matching(id: String): Option[(String, Int)] =
        Release.choice(covered, Release.AFP_Checkout(id))
          .map(c => (c.release.tag, c.covered.distance))
      assert(matching("0726d9f1e0bf") == Some((newest_first.head.tag, 0)))
      assert(matching("0726d9f1e0bf" + "0" * 28 + "+") == Some((newest_first.head.tag, 0)))
      assert(matching("aaaaaaaaaaaa") == Some(("index-plain-20261101-afp-aaaaaaaaaaaa", 0)))
      assert(matching("cccccccccccc") == Some((newest_first(2).tag, 2)))
      assert(matching("dddddddddddd").isEmpty && matching("bbbbbbbbbbbb").isEmpty &&
        matching("").isEmpty)
      assert(Data.relative_path("a/b.c").implode == "a/b.c")
      for (bad <- List("../a", "/a", "a/../b", "$A/b", "~/a", "a//b"))
        assert(Exn.result(Data.relative_path(bad)).isInstanceOf[Exn.Exn[?]],
          "Bad relative path accepted: " + bad)
    }

    // A clone gets the release of its newest covered ancestor: after the release, one AFP
    // changeset without effect on the index and one without a release yet, then local
    // changesets, one of them public after a push to another repository.
    Isabelle_System.with_tmp_dir("isasearch-clone") { dir =>
      def commit(hg: Mercurial.Repository, path: String, message: String): String = {
        val file = hg.root + Path.explode(path)
        Isabelle_System.make_directory(file.dir)
        File.write(file, message)
        hg.command("commit", args = "-A -u test -d " + Bash.string("0 0") + " -m " +
          Bash.string(message)).check
        hg.log(rev = ".", template = "{node}")
      }
      val upstream = Mercurial.init_repository(dir + Path.basic("afp"))
      val base = commit(upstream, "thys/A/A.thy", "released")
      val site = commit(upstream, "web/index.html", "site")
      commit(upstream, "thys/C/C.thy", "unreleased")
      val hg = Mercurial.clone_repository(upstream.root.implode, dir + Path.basic("clone"))
      commit(hg, "thys/B/B.thy", "pushed elsewhere")
      hg.command("phase", args = "--public -r .").check
      commit(hg, "metadata/entries/B.toml", "local")
      File.write(hg.root + Path.explode("thys/A/A.thy"), "uncommitted")
      val release = Release.Info("index-plain-20261111-afp-" + base.take(12), "", Nil)
      val listing = Map("revisions" -> Map(
        site -> Map[String, Any]("release" -> release.tag, "distance" -> 1)))
      val covered = Release.covered(List(release), Some(listing))
      val checkout = Release.AFP_Checkout(hg.id(rev = ""), Some(hg))
      val chosen = Release.choice(covered, checkout, upstream.root.implode).get
      assert(chosen.covered.id == site && chosen.published == 1 && chosen.local == 2 &&
        !chosen.by_phase && chosen.changed == List("A", "B", "C"), chosen.toString)
      assert(chosen.differences(checkout) == List(
        "1 AFP changeset since the release, without effect on the index",
        "1 AFP changeset without a release yet",
        "2 local changesets not in the AFP repository",
        "uncommitted changes",
        "Not in the index: the changes to A, B, C (isasearch_index builds an index with them)"),
        chosen.differences(checkout).toString)
      // Without an answer from the AFP repository, the phases tell them apart.
      val by_phase =
        Release.choice(covered, checkout, (dir + Path.basic("missing")).implode).get
      assert(by_phase.by_phase && by_phase.published == 2 && by_phase.local == 1 &&
        by_phase.differences(checkout)
          .contains("Local means not public here: the AFP repository did not answer"),
        by_phase.toString)
      // Without a listing, a release covers its own revision.
      assert(Release.choice(Release.covered(List(release), None), checkout)
        .exists(c => c.covered.id == base.take(12) && c.published == 3 && c.local == 1))
    }


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
        // The free port of a server is held for it until it starts.
        val url = new java.net.URI(servers.config.string(Endpoint.OpenAI.url))
        val taken =
          try {
            new java.net.ServerSocket(url.getPort, 1, java.net.InetAddress.getLoopbackAddress)
              .close()
            false
          }
          catch { case _: java.io.IOException => true }
        assert(taken, "Port of a waiting server reserved")
      }
      // A started server replaces an endpoint, whose key it must not receive.
      for (setting <- Endpoint.OpenAI_Embedding.key_settings) {
        val keyed = shipped.updated(setting, "secret")
        assert(Exn.result(Llama_Server.command(keyed, Llama_Server.Role.Embedding, 8080))
          .isInstanceOf[Exn.Exn[?]], "Key of a replaced endpoint accepted: " + setting)
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


    /* requests and local sources */

    {
      def rejected(body: => Any): Boolean =
        try { body; false }
        catch { case _: Search.Bad_Request => true }
      assert(Search.parameters("query=a%20b&kind") == Map("query" -> "a b", "kind" -> ""))
      assert(rejected(Search.parameters("id=%zz")), "Malformed escape")
      assert(Search.integer(Map("limit" -> "7"), "limit", 100) == 7 &&
        Search.integer(Map.empty, "limit", 100) == 100)
      assert(rejected(Search.integer(Map("limit" -> "many"), "limit", 100)))

      val hosts = Search.hosts("Search.Example.org, proxy")
      for (header <- List("localhost:5001", "LOCALHOST", "127.0.0.1:5001", "[::1]:5001",
          "search.example.org", "proxy:8080"))
        assert(hosts(Search.host_name(header)), "Host of this server: " + header)
      for (header <- List("evil.example:5001", "localhost.evil.example", "[::1", "", ":5001"))
        assert(!hosts(Search.host_name(header)), "Foreign host: " + header)
      assert(!Search.loopback_hosts(Search.host_name("search.example.org")))

      // Only files below the roots of indexed sources, whatever a record of an index names.
      def local(file: String): Option[Path] = Search.Local_Sources.file(Map("file" -> file))
      for (file <- List("ISABELLE_HOME/src/HOL/HOL.thy", "ISABELLE_HOME/src/Pure/../HOL/HOL.thy"))
        assert(local(file).contains(Path.explode("$ISABELLE_HOME/src/HOL/HOL.thy").expand),
          "Local file of the sources: " + file)
      for (file <- List("ISABELLE_HOME/../ROOTS", "ISABELLE_HOME/src/../../ROOTS",
          "ISABELLE_HOME//etc/passwd", "ISABELLE_HOME/~/.profile", "ISABELLE_HOME/$HOME/.profile",
          "ISABELLE_HOME_USER/etc/settings", "HOME/.profile", "USER_HOME/.profile",
          "ISASEARCH_HOME/etc/options", "/etc/passwd", "ISABELLE_HOME", "ISABELLE_HOME/", ""))
        assert(local(file).isEmpty, "Local file outside the sources: " + file)

      val text = "theory T\n\nlemma a:\n  \"P\"\n\nend\n"
      assert(Search.Local_Sources.lines(text, Map("src" -> "lemma a:\n  \"P\"")) == (3 until 5))
      assert(Search.Local_Sources.lines(text, Map("src" -> "lemma b:\n  \"Q\"")).isEmpty,
        "No lines of a source that the file lacks")
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
