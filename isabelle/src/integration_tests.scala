/*  Title:      IsaSearch/isabelle/src/integration_tests.scala

End-to-end tests of the command-line tools in an isolated Isabelle user directory, against a
deterministic local inference stub. No real model is contacted.
*/

package isabelle.isasearch


import isabelle._

import java.net.{InetAddress, InetSocketAddress, URI}
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.nio.file.Files
import java.nio.file.attribute.PosixFilePermissions
import java.util.concurrent.Executors
import com.sun.net.httpserver.{HttpExchange, HttpServer}


object Integration_Tests {
  import Data._


  /** checks **/

  def check(condition: Boolean, message: => String): Unit =
    if (!condition) error("Integration test failed: " + message)

  def same(a: JSON.T, b: JSON.T): Boolean = canonical(a) == canonical(b)


  /** isolated Isabelle user directory **/

  // Child processes read Isabelle settings afresh: they receive only a basic process
  // environment, and USER_HOME selects a user directory that registers this component.
  class Environment(root: Path) {
    private val home = root + Path.basic("home")
    private val isabelle = Path.explode("$ISABELLE_HOME/bin/isabelle").expand

    val user: Path = {
      val real_home = Path.explode("$USER_HOME").expand.implode
      val real_user = Path.explode("$ISABELLE_HOME_USER").expand.implode
      home + Path.explode(Library.try_unprefix(real_home + "/", real_user)
        .getOrElse(error("ISABELLE_HOME_USER outside USER_HOME")))
    }

    val env: java.util.Map[String, String] = {
      val result = new java.util.HashMap[String, String]
      for {
        name <- List("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
          "TMPDIR", "TERM")
        value <- proper_string(System.getenv(name))
      } result.put(name, value)
      result.put("USER_HOME", home.absolute.implode)
      result.put("ISASEARCH_TEST_KEY", "test-key")
      result
    }

    def register(components: Path*): Unit =
      File.write(user + Path.explode("etc/components"),
        components.map(_.absolute.implode).mkString("", "\n", "\n"))

    // A repository clone of Isabelle initializes contrib components in user settings and
    // keeps its heaps in the user directory; these heaps are shared read-only.
    Isabelle_System.make_directory(user + Path.basic("etc"))
    File.write(user + Path.explode("etc/settings"),
      "ISABELLE_COMPONENTS_BASE=" + quote(Isabelle_System.getenv("ISABELLE_COMPONENTS_BASE")) +
        "\nif [ -f \"$ISABELLE_HOME/Admin/components/main\" ]; then\n" +
        "  init_components \"$ISABELLE_COMPONENTS_BASE\" " +
        "\"$ISABELLE_HOME/Admin/components/main\"\n" +
        "  ISABELLE_HEAPS_SYSTEM=" + quote(Isabelle_System.getenv("ISABELLE_HEAPS")) + "\n" +
        "fi\n" +
        "ISABELLE_TOOL_JAVA_OPTIONS=\"-Djava.awt.headless=true -Xms256m -Xmx4g -Xss16m\"\n")
    register(component.expand)

    private def script(tool: String, args: List[String]): String =
      File.bash_path(isabelle) + " " + Bash.strings(("isasearch_" + tool) :: args)

    def run(tool: String, args: List[String], ok: Boolean = true): Process_Result = {
      val result = Isabelle_System.bash(script(tool, args), env = env, strict = false,
        watchdog = Bash.Watchdog(Time.seconds(240)))
      check(result.ok == ok, "isasearch_" + tool + " " + args.mkString(" ") + "\n" +
        cat_lines(result.out_lines ::: result.err_lines))
      result
    }

    def json(result: Process_Result): Obj =
      obj(JSON.parse(result.out_lines.findLast(_.startsWith("{"))
        .getOrElse(error("No JSON output:\n" + result.out))))

    def process(tool: String, args: List[String]): Bash.Process =
      Bash.process(script(tool, args), env = env, redirect = true)
  }


  /** inference stub **/

  class Stub(vectors: Map[String, List[Double]]) {
    @volatile var mode = "ok"
    @volatile var llm_up = true
    @volatile var transient = 0
    @volatile var completion_mode = "ok"
    @volatile var completion_text = "<BEGIN>VERDICT: DUPLICATE\nSame statement.<END>"
    @volatile var fail_input_contains = ""
    @volatile var fail_completion_contains = ""
    @volatile var empty_completions = 0
    private val log = scala.collection.mutable.ListBuffer.empty[(String, Obj)]

    def calls: List[(String, Obj)] = synchronized { log.toList }

    def prompt(body: Obj): String =
      if (body.contains("prompt")) str(body, "prompt")
      else list(body.getOrElse("messages", Nil)).headOption.map(m => str(obj(m), "content"))
        .getOrElse("")

    def completions(since: Int = 0, health: Boolean = false): List[Obj] =
      calls.drop(since).collect {
        case (path, body) if path.endsWith("chat/completions") &&
          (health || prompt(body) != "Reply with OK.") => body
      }

    private def take(counter: () => Int, decrement: () => Unit): Boolean = synchronized {
      if (counter() > 0) { decrement(); true } else false
    }

    private def payload(path: String, body: Obj): Option[JSON.T] =
      if (path.endsWith("embeddings") || path == "/api/embed") {
        val inputs = strings(body, "input")
        if (fail_input_contains.nonEmpty && inputs.exists(_.contains(fail_input_contains)))
          None
        else if (take(() => transient, () => transient -= 1)) None
        else {
          if (mode == "timeout") Thread.sleep(2200)
          val vs: List[List[Double]] =
            if (mode == "dimension") inputs.map(_ => List(1.0))
            else if (mode == "mismatch") inputs.map(_ => List(0.0, 0.0, 1.0))
            else inputs.map(t => vectors.getOrElse(t, List(1.0, 0.0, 0.0)))
          if (path == "/api/embed") Some(Map("embeddings" -> vs))
          else if (mode == "indices")
            Some(Map("data" -> vs.map(v => Map("index" -> 0, "embedding" -> v))))
          else
            Some(Map("data" -> vs.zipWithIndex.map { case (v, i) =>
              Map("index" -> i, "embedding" -> v) }.reverse))
        }
      }
      else {
        val text = prompt(body)
        if (!llm_up ||
            fail_completion_contains.nonEmpty && text.contains(fail_completion_contains)) None
        else {
          val output =
            if (text != "Reply with OK." && take(() => empty_completions,
                () => empty_completions -= 1) || completion_mode == "empty") "<BEGIN> <END>"
            else completion_text
          if (path.endsWith("chat/completions"))
            Some(Map("choices" -> List(Map("message" -> Map("content" -> output),
              "finish_reason" -> "stop"))))
          else Some(Map("response" -> output, "content" -> output, "done_reason" -> "stop"))
        }
      }

    private val server =
      HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress, 0), 0).nn
    server.setExecutor(Executors.newCachedThreadPool())
    server.createContext("/", { (http: HttpExchange | Null) =>
      val exchange = http.nn
      try {
        val path = exchange.getRequestURI.nn.getPath.nn
        val body = obj(JSON.parse(Bytes.read_stream(exchange.getRequestBody.nn).text))
        synchronized { log += path -> body }
        val authorized =
          proper_string(exchange.getRequestHeaders.nn.getFirst("Authorization"))
            .contains("Bearer test-key")
        (if (authorized) payload(path, body) else None) match {
          case Some(result) =>
            val bytes = UTF8.bytes(JSON.Format(result))
            exchange.getResponseHeaders.nn.set("Content-Type", "application/json")
            exchange.sendResponseHeaders(200, bytes.length.toLong)
            using(exchange.getResponseBody.nn)(_.write(bytes))
          case None => exchange.sendResponseHeaders(if (authorized) 503 else 401, -1)
        }
      }
      catch { case scala.util.control.NonFatal(_) => }
      finally { exchange.close() }
    })
    server.start()

    def url: String = "http://127.0.0.1:" + server.getAddress.nn.getPort

    def close(): Unit = server.stop(0)
  }


  /** interchange fixtures **/

  val fixture_prompts: Obj = Map(
    "embed" -> "{doc_src}",
    "retrieve" -> "{search_query}",
    "search_refine" -> "Expand {search_query}",
    "duplicate_judge" -> "Compare {item_a} and {item_b}"
  )

  // Three documents per corpus in entries A, B, C; returns the vector of each embedding input.
  def fixture(
    root: Path,
    metric: Distance_Metric = Distance_Metric.Cosine,
    dimension: Int = 3,
    metadata: Boolean = false
  ): (Path, Map[String, List[Double]]) = {
    val exported = Isabelle_System.make_directory(root + Path.basic("export"))
    var embeddings = Map.empty[String, List[Double]]
    val corpora = Index.kinds.map { kind =>
      val directory = Isabelle_System.make_directory(exported + Path.basic(kind.name))
      val documents = List("A", "B", "C").zipWithIndex.map { case (e, i) =>
        val id = "AFP/thys/" + e + "/T.thy|" + kind.name + i
        val command = if (kind == Corpus_Kind.Theorems) "lemma" else "definition"
        val source = command + " x" + i + ": \"a + b = b + a\""
        val description = "Commutativity ∀α 😀 " + kind.name + " " + i
        val text = description + "\n\n" + source
        val (x, y) = List((1.0, 0.0), (0.99, 0.01), (0.0, 1.0))(i)
        val vector = (x :: y :: List.fill(dimension - 2)(0.0)).map(_.toFloat)
        embeddings += text -> vector.map(_.toDouble)
        val checksum = new java.util.zip.Adler32()
        checksum.update(UTF8.bytes(source))
        val record = Map(
          "id" -> id, "src" -> source, "entity_kname" -> ("T.x" + i + "|thm"), "entry" -> e,
          "entry_date" -> "2026-01-01", "command" -> command, "session" -> e,
          "start_line" -> (i + 1), "consts" -> List("T.shared"), "typs" -> Nil,
          "kind" -> kind.name, "checksum" -> checksum.getValue, "llm_description" -> description,
          "embedding_input" -> text,
          "description_artifact" -> Map(
            "llm_description" -> (Prompt.Begin + description + Prompt.End),
            "zlib.adler32_checksum" -> checksum.getValue))
        (record, vector.toArray)
      }
      File.write(directory + Path.basic(Index_Format.documents),
        documents.map(d => JSON.Format(d._1)).mkString("", "\n", "\n"))
      Bytes.write(directory + Path.basic(Index_Format.vectors),
        Bytes(documents.flatMap(d => bytes(d._2)).toArray))
      Map(
        "kind" -> kind.name,
        "count" -> documents.size,
        "dimension" -> dimension,
        "metric" -> metric.name,
        "recipe" -> Map("model" -> "fixture", "backend" -> "openai", "max_characters" -> 8000,
          "add_metadata" -> metadata, "document_model" -> "fixture",
          "prompts" -> fixture_prompts),
        "files" -> Index_Format.data_files.map(f => f -> file_hash(directory + Path.basic(f)))
          .toMap)
    }
    write(exported + Path.basic(Index_Format.manifest),
      Map("format" -> Index_Format.name, "version" -> Index_Format.version, "corpora" -> corpora))
    (exported, embeddings)
  }

  def csv(path: Path, header: List[String], rows: List[Map[String, String]]): Unit = {
    def field(s: String): String = "\"" + s.replace("\"", "\"\"") + "\""
    File.write(path, (header :: rows.map(r => header.map(r.getOrElse(_, ""))))
      .map(_.map(field).mkString(",")).mkString("", "\r\n", "\r\n"))
  }


  /** API and benchmark **/

  def api_and_benchmark(progress: Progress): Unit =
    Isabelle_System.with_tmp_dir("isasearch-test") { root =>
      val env = new Environment(root)
      val (plain, vectors) = fixture(root + Path.basic("plain"))
      val (metadata, _) = fixture(root + Path.basic("metadata"), metadata = true)
      val (l2, _) = fixture(root + Path.basic("l2"), metric = Distance_Metric.Squared_Euclidean)
      val (large, _) = fixture(root + Path.basic("large"), dimension = 2048)
      progress.echo("Component tests on imported fixtures ...")
      env.run("test", List(plain, l2, large).map(_.implode))
      env.run("import", List("-f", plain.implode, "-i", "plain"))
      env.run("import", List("-f", metadata.implode, "-i", "metadata"))
      val stub = new Stub(vectors)
      try {
        var config: Obj = Map(
          "embedding_backend" -> "openai",
          "openai_embedding_model" -> "fixture",
          "openai_embedding_base_url" -> (stub.url + "/v1"),
          "openai_base_url" -> (stub.url + "/v1"),
          "openai_api_key_env" -> "ISASEARCH_TEST_KEY",
          "llm_backend" -> "none",
          "llm_request_timeout" -> 2,
          "llm_attempts" -> 1,
          "enable_llm_output_cache" -> false)
        val config_path = root + Path.basic("config.json")
        def configure(changes: (String, JSON.T)*): Unit = {
          config = config ++ changes
          write(config_path, config)
        }
        def search(args: String*): List[String] =
          List("-c", config_path.implode, "-i", "plain") ::: args.toList
        configure()

        progress.echo("Search and HTTP API ...")
        check(env.json(env.run("search", search("commutativity"))).contains("results"),
          "search results")
        check(stub.completions(health = true).isEmpty, "search without LLM")
        env.run("search", search("-r", "commutativity"), ok = false)
        http_api(env, stub, config_path)

        progress.echo("Packaged index ...")
        val packaged = Path.explode(env.run("index_build",
          List("-i", "plain", "-D", (root + Path.basic("packages")).implode))
          .out_lines.filter(_.nonEmpty).last)
        val archive = packaged + Path.basic("plain.db")
        val archive_hash = file_hash(archive)
        Files.setPosixFilePermissions(archive.java_path,
          PosixFilePermissions.fromString("r--------"))
        env.register(component.expand, packaged)
        Isabelle_System.rm_tree(env.user + Path.explode("isasearch/indexes/plain"))
        env.run("search", search("relocated"))
        check(file_hash(archive) == archive_hash, "packaged index unchanged")

        progress.echo("Inference backends and failures ...")
        for (backend <- List("openai", "ollama", "llamacpp")) {
          configure("llm_backend" -> backend,
            "embedding_backend" -> (if (backend == "ollama") "ollama" else "openai"),
            (backend + "_query_model") -> "fixture",
            "ollama_base_url" -> stub.url, "llamacpp_base_url" -> stub.url)
          env.run("search", search("-r", "commutativity"))
        }
        stub.transient = 1
        env.run("search", search("retry"))
        check(stub.transient == 0, "transient failure retried")
        stub.mode = "indices"
        env.run("search", search("test"), ok = false)
        configure("embedding_attempts" -> 1)
        for (mode <- List("timeout", "dimension", "mismatch")) {
          stub.mode = mode
          env.run("search", search("test"), ok = false)
        }
        stub.mode = "ok"
        configure("llm_backend" -> "openai", "embedding_backend" -> "openai",
          "openai_query_model" -> "fixture")
        stub.completion_mode = "empty"
        env.run("search", search("-r", "test"), ok = false)
        stub.completion_mode = "ok"
        stub.llm_up = false
        env.run("search", search("-r", "test"), ok = false)
        stub.llm_up = true
        configure("llm_attempts" -> 2)
        stub.empty_completions = 1
        val before_retry = stub.calls.size
        env.run("search", search("-r", "retry empty"))
        val retries = stub.completions(since = before_retry)
        check(retries.size == 2, "empty completion retried")
        check(num(retries.last, "temperature", 0) == 0.3, "retry temperature")

        progress.echo("Query cache ...")
        configure("enable_llm_output_cache" -> true)
        val first = env.json(env.run("search", search("-r", "cached query")))
        val second = env.json(env.run("search", search("-r", "cached query")))
        check(!bool(first, "cache_hit") && bool(second, "cache_hit"), "query cache hit")
        check(num(second, "duration", 0) >= num(second, "elapsed_duration", 0),
          "replayed duration")
        // llama.cpp omits the model from its request body, but its cache must still follow
        // the configured model when a server changes models.
        configure("llm_backend" -> "llamacpp", "llamacpp_query_model" -> "model-a")
        val original_completion = stub.completion_text
        for ((model, answer, cached) <- List(("model-a", "Model A answer", false),
            ("model-b", "Model B answer", false), ("model-b", "Model B answer", true),
            ("model-a", "Model A answer", true))) {
          configure("llamacpp_query_model" -> model)
          stub.completion_text = Prompt.Begin + answer + Prompt.End
          val response = env.json(env.run("search", search("-r", "model cache")))
          check(str(response, "refined_query") == answer && bool(response, "cache_hit") == cached,
            "model-specific cache: " + model)
        }
        stub.completion_text = original_completion
        configure("llm_backend" -> "openai", "enable_llm_output_cache" -> false)

        progress.echo("Benchmark ...")
        benchmark(env, root, config_path)

        progress.echo("Duplicate analysis ...")
        duplicates(env, stub, root, config_path, configure)
      }
      finally { stub.close() }
    }

  def http_api(env: Environment, stub: Stub, config_path: Path): Unit = {
    val server = env.process("server", List("-c", config_path.implode, "-i", "plain", "-p", "0"))
    try {
      val api = {
        var url = ""
        val output = new StringBuilder
        while (url.isEmpty) {
          val line = proper_value(server.stdout.readLine())
            .getOrElse(error("API server stopped:\n" + output))
          output ++= line + "\n"
          url = Library.try_unprefix("IsaSearch API: ", line).map(Library.trim_string)
            .getOrElse("")
        }
        url
      }
      val client = HttpClient.newHttpClient().nn

      def get(request: String): (Int, Obj) = {
        val response = client.send(
          HttpRequest.newBuilder(URI.create(api + request)).nn.GET().nn.build(),
          HttpResponse.BodyHandlers.ofString()).nn
        (response.statusCode(), obj(JSON.parse(response.body().nn)))
      }

      val (_, capabilities) = get("/capabilities")
      check(bool(capabilities, "embedding_available") && !bool(capabilities, "query_expansion"),
        "capabilities")
      for ((query, status) <- List(("?query=test&refine_query=true", 503), ("?query=", 400),
          ("?query=test&kind=bad", 400)))
        check(get("/search" + query)._1 == status, "HTTP status for " + query)
      val (code, found) = get("/search?query=test")
      check(code == 200 && list(found("results")).size == 3, "search over HTTP")
      stub.mode = "dimension"
      check(get("/search?query=unavailable")._1 == 503, "unavailable embedding service")
      check(!bool(get("/capabilities")._2, "embedding_available"), "refreshed capabilities")
      stub.mode = "ok"
    }
    finally { server.terminate() }
  }

  def benchmark(env: Environment, root: Path, config_path: Path): Unit = {
    val dataset = root + Path.basic("benchmark.csv")
    val target = JSON.Format(List(Map("entity_kname" -> "T.x0|thm")))
    csv(dataset,
      List("ID", "Target Identifier", "Title query", "Natural language query", "Skip",
        "Annotation"),
      List(
        Map("ID" -> "test", "Target Identifier" -> target, "Title query" -> "commutativity",
          "Natural language query" -> "The sum,\nof two numbers commutes."),
        Map("ID" -> "solutions-to-pells-equation", "Target Identifier" -> target,
          "Title query" -> "Changed title that must not be used",
          "Natural language query" -> "Changed natural query that must not be used"),
        Map("ID" -> "skip", "Skip" -> "true", "Annotation" -> "fixture")))
    val reports = root + Path.basic("reports")
    env.run("benchmark", List("-c", config_path.implode, "-i", "plain", "-m", "metadata",
      "-f", dataset.implode, "-s", "all", "-D", reports.implode))
    val paper = Benchmark.paper_queries()
    val outputs = File.find_files(reports, _.file_name.endsWith(".json"))
    check(outputs.size == 12, "benchmark outputs")
    for (output <- outputs) {
      val data = read(output)
      if (output.file_name == "results.json") {
        val accuracy = object_at(object_at(object_at(data, "summary"), "all_queries"),
          "top_k_accuracy")
        check(num(accuracy, "average", 0) == 1 && num(accuracy, "sample_size", 0) == 5,
          "benchmark summary")
        val replayed = object_at(object_at(data, "solutions-to-pells-equation"), "queries")
          .map { case (kind, q) => kind -> Map("query" -> obj(q)("query"),
            "source" -> obj(q)("source")) }
        check(same(replayed, paper.for_row(Map("ID" -> "solutions-to-pells-equation"))),
          "paper queries replayed")
        val metadata = object_at(object_at(data, "test"), "metadata")
        check(same(metadata("target_identifier"), List(Map("entity_kname" -> "T.x0|thm"))),
          "target identifier")
        check(same(metadata("skipped_queries"),
          Map("Noisy natural language query" -> "paper_noisy_query_missing")), "skipped queries")
        check(bool(object_at(object_at(data, "skip"), "metadata"), "skipped"), "skipped row")
      }
      else check(same(data("query_inputs"), paper.provenance), "query input provenance")
    }
  }

  def duplicates(
    env: Environment,
    stub: Stub,
    root: Path,
    config_path: Path,
    configure: Seq[(String, JSON.T)] => Unit
  ): Unit = {
    def analysis(directory: Path, args: String*): Path = {
      env.run("duplicates", List("-c", config_path.implode, "-i", "plain", "-e", "A") :::
        args.toList ::: List("-D", directory.implode))
      File.find_files(directory, p => p.file_name.startsWith("experiment_") &&
        p.file_name.endsWith(".json")).head
    }
    def sections(report: Obj): List[Obj] = object_at(report, "sections").values.map(obj).toList
    def first_candidates(section: Obj): List[Obj] =
      list(obj(list(obj(list(section("entries")).head)("items")).head)("candidates")).map(obj)

    val report = read(analysis(root + Path.basic("reports"), "-k", "all", "-x"))
    check(bool(report, "llm_judge"), "judged duplicates")
    for (section <- sections(report)) {
      check(num(object_at(section, "self_retrieval"), "failure_fraction", 1) == 0,
        "self retrieval")
      for {
        entry <- list(section("entries")).map(obj)
        item <- list(entry("items")).map(obj)
        candidate <- list(item("candidates")).map(obj)
      } check(str(candidate, "entry") != "A", "own entry excluded")
    }

    // Exhausted judge failures preserve the run, remain uncached, and retry next time.
    configure(List("enable_llm_output_cache" -> true))
    stub.fail_completion_contains = "Compare "
    val before = stub.calls.size
    val failed_path = analysis(root + Path.basic("failed-judge"), "-a")
    val failed = read(failed_path)
    val section = object_at(object_at(failed, "sections"), "definitions")
    check(num(object_at(section, "aggregates"), "judge_failures", 0) == 1, "judge failure")
    val candidate = first_candidates(section).head
    check(candidate.contains("judge_error") && !candidate.contains("verdict"), "unjudged pair")
    check(stub.completions(since = before).count(b => stub.prompt(b).startsWith("Compare ")) == 2,
      "judge retried")
    for ((suffix, exact) <- List(("possible", false), ("near-exact", true))) {
      val view = failed_path.dir + Path.basic(failed_path.drop_ext.file_name + "_" + suffix + ".md")
      check(File.read(view) == Duplicate_Report.render(failed, near_exact_only = exact),
        "report view " + suffix)
    }
    stub.fail_completion_contains = ""
    val recovered = read(analysis(root + Path.basic("retry-judge")))
    val retried = object_at(object_at(recovered, "sections"), "definitions")
    check(num(object_at(retried, "aggregates"), "judge_failures", 1) == 0 &&
      str(first_candidates(retried).head, "verdict") == "DUPLICATE", "judge retry")
  }


  /** corpus build from the registered AFP **/

  def afp_build(progress: Progress): Unit = {
    val afp_base = Isabelle_System.getenv("AFP_BASE")
    if (afp_base.isEmpty) progress.echo_warning("Skipped AFP build: no registered AFP")
    else Isabelle_System.with_tmp_dir("isasearch-afp") { root =>
      val afp = Path.explode(afp_base)
      val env = new Environment(root)
      val stub = new Stub(Map.empty)
      try {
        val cfg = root + Path.basic("config.json")
        var config: Obj = Map(
          "embedding_backend" -> "openai",
          "openai_embedding_model" -> "fixture",
          "openai_embedding_base_url" -> (stub.url + "/v1"),
          "openai_base_url" -> (stub.url + "/v1"),
          "openai_api_key_env" -> "ISASEARCH_TEST_KEY",
          "llm_backend" -> "openai",
          "openai_document_model" -> "fixture",
          "enable_llm_output_cache" -> false,
          "isabelle_build_jobs" -> 2)
        def configure(changes: (String, JSON.T)*): Unit = {
          config = config ++ changes
          write(cfg, config)
        }
        def unset(key: String): Unit = {
          config = config - key
          write(cfg, config)
        }
        def run(tool: String, args: List[String], ok: Boolean = true,
            index: String = "afp-test"): Process_Result =
          env.run(tool, List("-c", cfg.implode, "-i", index) ::: args, ok = ok)
        def found(): List[Obj] =
          list(env.json(run("search", List("truth")))("results")).map(obj)
        def described(): Int = stub.completions().size
        def errors(result: Process_Result): String = cat_lines(result.err_lines)
        def output(result: Process_Result): String = result.out + "\n" + errors(result)
        def manifest(name: String): Obj = {
          val index = env.user + Path.explode("isasearch/indexes/" + name)
          read(index + Path.basic(str(read(index + Path.basic("current.json")), "generation")) +
            Path.basic(Index_Format.manifest))
        }
        configure()

        progress.echo("Corpus build from the registered AFP ...")
        // "all" covers the AFP and the HOL distribution, without the documentation group.
        val all = Corpus_Build.sessions(Config(Map.empty), Options.init(), afp, List("all"))
        check(all.contains("Example-Submission") && all.contains("HOL-Library") &&
          !all.contains("Codegen") && !all.contains("Datatypes"), "sessions of all")
        check(errors(run("index", List("Example-Submission"), ok = false))
          .contains("No registered AFP"), "missing AFP reported")
        // Both registration forms must resolve the same AFP root.
        for (registration <- List(afp, afp + Path.basic("thys"))) {
          env.register(registration, component.expand)
          run("index", List("Example-Submission"))
        }
        val descriptions = stub.completions()
        check(descriptions.size == 2, "resumption regenerated unchanged descriptions")

        // Python description artifacts seed an empty store, which a build then reuses.
        val artifact = root + Path.basic("document_descriptions.json")
        write(artifact, descriptions.zipWithIndex.map { case (body, n) =>
          n.toString -> Map("llm_description" -> stub.completion_text,
            "zlib.adler32_checksum" -> 0, "model" -> "fixture", "prompt" -> stub.prompt(body))
        }.toMap)
        Isabelle_System.rm_tree(env.user + Path.explode("isasearch/llm_cache"))
        check(run("seed", List(artifact.implode)).out.contains("2 stored"), "seeded store")
        run("index", List("-n", "Example-Submission"))
        check(described() == 2, "seeded descriptions generated again")

        val results = found()
        check(results.size == 2 && results.forall(d => str(d, "entry") == "Example-Submission"),
          "searchable entry")
        // AFP sources link to the repository, not to the Isabelle library.
        check(results.forall(d => str(d, "theory_url").isEmpty && str(d, "remote_url").nonEmpty),
          "AFP links")
        run("index_build", List("-D", (root + Path.basic("components")).implode))
        run("duplicates", List("-k", "theorems", "-e", "Example-Submission", "-J",
          "-D", (root + Path.basic("reports")).implode))
        val dataset = root + Path.basic("benchmark.csv")
        csv(dataset, List("ID", "Target Identifier", "Title query"),
          List(Map("ID" -> "truth",
            "Target Identifier" -> JSON.Format(List(Map("id" -> results.head("id")))),
            "Title query" -> "truth")))
        run("benchmark", List("-f", dataset.implode, "-D", (root + Path.basic("reports")).implode))

        progress.echo("Corpus updates on an AFP copy ...")
        // Use an isolated AFP copy to exercise changed/deleted sources and failed-build resumption.
        val copied = root + Path.basic("afp")
        Isabelle_System.make_directory(copied + Path.basic("etc"))
        for (name <- List("settings", "version"))
          Isabelle_System.copy_file(afp + Path.explode("etc/" + name), copied + Path.basic("etc"))
        Isabelle_System.copy_dir(afp + Path.explode("thys/Example-Submission"),
          Isabelle_System.make_directory(copied + Path.explode("thys/Example-Submission")),
          direct = true)
        File.write(copied + Path.explode("thys/ROOTS"), "Example-Submission\n")
        File.write(Isabelle_System.make_directory(copied + Path.explode("metadata/entries")) +
          Path.basic("Example-Submission.toml"),
          "title = \"Metadata regression title\"\nabstract = \"Metadata regression abstract\"\n")
        env.register(copied, component.expand)
        configure("embedding_attempts" -> 1)
        // Sources are identified by $AFP paths, so relocating the checkout keeps the build and
        // every source identity, unless the platform exports canonical paths (temporary
        // directories on macOS). Explicitly accept this possible fixture migration, then
        // restore the guard for subsequent update tests.
        configure("allow_large_prune" -> true)
        run("index", List("Example-Submission"))
        unset("allow_large_prune")

        // A failing session is reported and left out; the other sessions are indexed, and the
        // FindFacts index of unchanged builds is reused.
        val failing = Isabelle_System.make_directory(copied + Path.explode("thys/Failing"))
        File.write(failing + Path.basic("ROOT"),
          "chapter AFP\n\nsession Failing = HOL +\n  theories Failing\n")
        File.write(failing + Path.basic("Failing.thy"),
          "theory Failing imports Main begin\nlemma \"False\" by simp\nend\n")
        File.write(copied + Path.explode("thys/ROOTS"), "Example-Submission\nFailing\n")
        val partial = run("index", List("Example-Submission", "Failing"), index = "afp-partial")
        check(output(partial).contains("Not indexed, failed (1): Failing"), "failed session")
        check(output(partial).contains("FindFacts index is current"), "shared FindFacts index")
        val partial_provenance = object_at(manifest("afp-partial"), "provenance")
        check(same(partial_provenance("sessions"), List("Example-Submission")) &&
          same(partial_provenance("unbuilt_sessions"), Map("Failing" -> "failed")),
          "unbuilt sessions recorded")

        // Only the flag changes: the base prompts folder remains configured.
        // Inspect actual LLM requests to ensure metadata reaches the model.
        val calls_before = stub.calls.size
        configure("add_metadata" -> true)
        check(output(run("index", List("-n", "Example-Submission"), index = "afp-metadata-test"))
          .contains("FindFacts index is current"), "FindFacts index shared by metadata build")
        val prompts = stub.completions(since = calls_before).map(stub.prompt)
        check(prompts.size == 2 && prompts.forall(p =>
          p.contains("Title: metadata regression title") &&
            p.contains("Abstract: metadata regression abstract")), "metadata prompts")
        val metadata_manifest = manifest("afp-metadata-test")
        // The copied AFP is not a Mercurial repository: its revision is unknown.
        val provenance = object_at(metadata_manifest, "provenance")
        check(str(object_at(provenance, "isabelle"), "identifier") ==
          Isabelle_System.getenv("ISABELLE_IDENTIFIER") &&
          str(object_at(provenance, "afp"), "version") == Isabelle_System.getenv("AFP_VERSION") &&
          object_at(provenance, "afp")("id") == null, "provenance")
        val metadata_describe =
          File.read(component + Path.explode("prompts/qwen3-gemma-with-metadata/describe.txt"))
        for (corpus <- list(metadata_manifest("corpora")).map(obj)) {
          val recipe = object_at(corpus, "recipe")
          check(bool(recipe, "add_metadata") &&
            str(object_at(recipe, "prompts"), "describe") == metadata_describe, "metadata recipe")
        }
        unset("add_metadata")

        // Session options apply to their session: quick_and_dirty admits the proof of Failing.
        configure("isabelle_session_options" -> Map("No_Such_Session" -> List("quick_and_dirty")))
        check(errors(run("index", List("Example-Submission"), ok = false, index = "afp-partial"))
          .contains("Unknown Isabelle session in isabelle_session_options: No_Such_Session"),
          "unknown session in session options")
        configure("isabelle_session_options" -> Map("Failing" -> List("quick_and_dirty")))
        File.write(failing + Path.basic("Failing.thy"),
          "theory Failing imports Main begin\nlemma \"False\" sorry\nend\n")
        check(output(run("index", List("Example-Submission", "Failing"), index = "afp-partial"))
          .contains("\nDescribed "), "sample of new descriptions")
        val admitted_provenance = object_at(manifest("afp-partial"), "provenance")
        check(same(admitted_provenance("sessions"), List("Example-Submission", "Failing")) &&
          same(admitted_provenance("unbuilt_sessions"), Map.empty[String, String]),
          "session options")
        unset("isabelle_session_options")

        // One call builds several indexes from one session build and keeps a log; the second
        // configuration reads the API key from a file instead of the environment.
        val key_file = root + Path.basic("api_key")
        File.write(key_file, "test-key\n")
        val second = root + Path.basic("second.json")
        write(second, config - "openai_api_key_env" ++
          Map("openai_api_key_file" -> key_file.implode, "add_metadata" -> true))
        check(errors(env.run("index", List("-c", cfg.implode, "-c", second.implode, "-i", "x"),
          ok = false)).contains("Pair each configuration"), "unpaired configuration")
        val logs = env.user + Path.explode("isasearch/logs")
        val logs_before = if (logs.is_dir) File.read_dir(logs) else Nil
        val both = output(env.run("index", List("-c", cfg.implode, "-i", "afp-test",
          "-c", second.implode, "-i", "afp-second", "Example-Submission")))
        check(both.contains("Prepared 2 of 2 theorems (2 reused, 0 generated;") &&
          both.contains("Using the session builds of index afp-test") &&
          both.contains("FindFacts index is current"), "shared session builds")
        check(bool(object_at(list(manifest("afp-second")("corpora")).map(obj).head, "recipe"),
          "add_metadata"), "second index")
        val new_logs = File.read_dir(logs).filterNot(logs_before.contains)
        check(new_logs.size == 1 &&
          File.read(logs + Path.basic(new_logs.head)).contains("Published index afp-second"),
          "index log")

        // A session whose build lost its PIDE exports is built again; -n leaves it out.
        val session_db = env.user + Path.basic("heaps") +
          Path.basic(Store(Options.init()).ml_settings.ml_identifier) +
          Store.log_db("Example-Submission")
        using(SQLite.open_database(session_db))(
          _.execute_statement("DELETE FROM isabelle_exports WHERE name LIKE 'PIDE/%'"))
        check(output(run("index", List("-n", "Example-Submission"), ok = false))
          .contains("Not indexed, missing PIDE exports (1): Example-Submission"),
          "missing PIDE exports reported")
        check(output(run("index", List("Example-Submission")))
          .contains("Building again, missing PIDE exports (1): Example-Submission") &&
          found().size == 2, "missing PIDE exports rebuilt")

        val theory = copied + Path.explode("thys/Example-Submission/Submission.thy")
        val original = File.read(theory)
        val body = original.take(original.lastIndexOf("end"))
        File.write(theory, body + "lemma added_fact: \"True\" by simp\nend\n")
        stub.fail_input_contains = "added_fact"
        run("index", List("Example-Submission"), ok = false)
        check(found().size == 2, "failed build keeps published generation")
        val descriptions_before = described()
        stub.fail_input_contains = ""
        run("index", List("-n", "Example-Submission"))
        check(found().size == 3, "resumed build")
        check(described() == descriptions_before,
          "saved description was not reused after embedding failure")
        File.write(theory, File.read(theory).replacing("added_fact: \"True\"" ->
          "added_fact: \"True \\<and> True\""))
        run("index", List("Example-Submission"))
        check(found().exists(d => str(d, "src").contains("True ∧ True")), "changed source")
        File.write(theory, original)
        run("index", List("Example-Submission"))
        check(found().size == 2, "deleted source")
        // Removing all selected facts is guarded, and cannot replace the published generation.
        configure("solr_query" -> "id:does-not-exist")
        check(errors(run("index", List("-n", "Example-Submission"), ok = false))
          .contains("Refusing to prune"), "pruning guarded")
        check(found().size == 2, "guarded generation kept")
      }
      finally { stub.close() }
    }
  }


  /** entry point **/

  def run(progress: Progress): Unit = {
    api_and_benchmark(progress)
    afp_build(progress)
    progress.echo("IsaSearch integration tests passed")
  }
}
