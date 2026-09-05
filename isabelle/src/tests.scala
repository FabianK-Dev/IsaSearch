/*  Title:      IsaSearch/isabelle/src/tests.scala

Component checks and cross-language compatibility tests.
*/

package isabelle.isasearch


import isabelle._


object Tests {
  def run(args: List[String]): Unit = {
    import Data._


    /* portable data and compatibility algorithms */

    assert(Data.distance(Array(1f, 2f), Array(2f, 4f), Distance_Metric.Squared_Euclidean) == 5.0)
    assert(math.abs(Data.distance(Array(1f, 2f), Array(2f, 4f), Distance_Metric.Cosine)) < 1e-12)
    assert(Data.floats(Data.bytes(Array(1f, -2f))).toList == List(1f, -2f))
    assert(Data.template("{{x}} {q}", Map("q" -> "{untouched}")) == "{x} {untouched}")
    assert(Duplicates.sequence_ratio("abcd", "bcde") == 0.75)
    val random = new Benchmark.Python_Random(129869)
    assert(
      (1 to 3).map(_ => random.random()).toList == List(
        0.053190780235274904,
        0.6151133794983927,
        0.19201231357249715
      )
    )
    assert(Benchmark.csv("ID,query\r\na,\"hello,\nworld\"\r\n").head("query") == "hello,\nworld")


    /* Python golden outputs */

    args.headOption.foreach { path =>
      val golden = read(Path.explode(path))
      for (item <- list(golden("similarity")).map(obj)) {
        val got = Duplicates.sequence_ratio(str(item, "a"), str(item, "b"))
        assert(
          math.abs(got - num(item, "ratio", 0)) < 1e-12,
          "SequenceMatcher parity: " + JSON.Format(item)
        )
      }
      val noise_rng = new Benchmark.Python_Random(129869)
      for (item <- list(golden("noise")).map(obj))
        assert(
          Benchmark.noisy(str(item, "input"), noise_rng) == str(item, "output"),
          "Noisy query parity"
        )
      for (item <- list(golden("metrics")).map(obj)) {
        val got = Benchmark.metrics(list(item("results")).map(obj), list(item("targets")).map(obj))
        object_at(item, "expected").foreach { case (k, v) =>
          assert(math.abs(number(got(k)) - number(v)) < 1e-12, "Metric parity: " + k)
        }
      }
      for (item <- list(golden("normalized")).map(obj))
        assert(Duplicates.normalized(str(item, "input")) == str(item, "expected"))
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
    }


    /* index import, readers, packaging, and failed imports */

    for ((source, n) <- args.drop(1).zipWithIndex) {
      val name = "test-" + n + "-" + UUID.random_string()
      val root = Index.import_index(Path.explode(source), name)
      using(new Index.Snapshot(root)) { snapshot =>
        using(new Index.Snapshot(root)) { second =>
          for ((kind, corpus) <- snapshot.corpora) {
            val docs = corpus.all.toList
            assert(docs.size == corpus.spec.count)
            for ((id, doc) <- docs) {
              val vector = corpus.vector(id)
              val hits = corpus.search(vector, corpus.spec.count)
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
                corpus
                  .search(vector, corpus.spec.count, str(doc, "entry"))
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
