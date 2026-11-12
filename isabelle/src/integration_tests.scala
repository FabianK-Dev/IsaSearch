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
      // The sources of fixtures stand in for the AFP, unless an AFP component is registered.
      result.put("AFP", (root + Path.basic("sources")).absolute.implode)
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
    // The key that requests must carry: none in place of a started server, which gets no key.
    @volatile var key = "test-key"
    @volatile var mode = "ok"
    @volatile var llm_up = true
    @volatile var transient = 0
    @volatile var completion_mode = "ok"
    @volatile var completion_text = "<BEGIN>VERDICT: DUPLICATE\nSame statement.<END>"
    @volatile var fail_input_contains = ""
    @volatile var fail_completion_contains = ""
    @volatile var truncate_completion_contains = ""
    @volatile var empty_completions = 0
    @volatile var health_failures = 0
    @volatile var ready: () => Boolean = () => true
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
          val truncated =
            truncate_completion_contains.nonEmpty && text.contains(truncate_completion_contains)
          val reason = if (truncated) "length" else "stop"
          if (path.endsWith("chat/completions"))
            Some(Map("choices" -> List(Map("message" -> Map("content" -> output),
              "finish_reason" -> reason))))
          else
            Some(Map("response" -> output, "content" -> output, "done_reason" -> reason,
              "truncated" -> truncated))
        }
      }

    private val server =
      HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress, 0), 0).nn
    server.setExecutor(Executors.newCachedThreadPool())
    server.createContext("/", { (http: HttpExchange | Null) =>
      val exchange = http.nn
      try {
        val path = exchange.getRequestURI.nn.getPath.nn
        // Like llama-server's health check: unauthenticated, unavailable while loading.
        if (path == "/health") {
          val loading = take(() => health_failures, () => health_failures -= 1) || !ready()
          exchange.sendResponseHeaders(if (loading) 503 else 200, -1)
        }
        else {
          val body = obj(JSON.parse(Bytes.read_stream(exchange.getRequestBody.nn).text))
          synchronized { log += path -> body }
          val authorized =
            proper_string(exchange.getRequestHeaders.nn.getFirst("Authorization")) ==
              proper_string(key).map("Bearer " + _)
          (if (authorized) payload(path, body) else None) match {
            case Some(result) =>
              val bytes = UTF8.bytes(JSON.Format(result))
              exchange.getResponseHeaders.nn.set("Content-Type", "application/json")
              exchange.sendResponseHeaders(200, bytes.length.toLong)
              using(exchange.getResponseBody.nn)(_.write(bytes))
            case None => exchange.sendResponseHeaders(if (authorized) 503 else 401, -1)
          }
        }
      }
      catch { case scala.util.control.NonFatal(_) => }
      finally { exchange.close() }
    })
    server.start()

    def port: Int = server.getAddress.nn.getPort

    def url: String = "http://127.0.0.1:" + port

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
  // A long source makes the first record exceed the 32766 bytes of a Solr doc value.
  def fixture(
    root: Path,
    metric: Distance_Metric = Distance_Metric.Cosine,
    dimension: Int = 3,
    metadata: Boolean = false,
    long_source: Boolean = false,
    references: Boolean = false,
    sources: Option[Path] = None
  ): (Path, Map[String, List[Double]]) = {
    val exported = Isabelle_System.make_directory(root + Path.basic("export"))
    var embeddings = Map.empty[String, List[Double]]
    val corpora = Index.kinds.map { kind =>
      val directory = Isabelle_System.make_directory(exported + Path.basic(kind.name))
      val documents = List("A", "B", "C").zipWithIndex.map { case (e, i) =>
        val id = "AFP/thys/" + e + "/T.thy|" + kind.name + i
        val command = if (kind == Corpus_Kind.Theorems) "lemma" else "definition"
        val padding = if (long_source && i == 0) " (* " + "x" * 40000 + " *)" else ""
        val source = command + " x" + i + ": \"a + b = b + a\"" + padding
        val description = "Commutativity ∀α 😀 " + kind.name + " " + i
        val text = description + "\n\n" + source
        val (x, y) = List((1.0, 0.0), (0.99, 0.01), (0.0, 1.0))(i)
        val vector = unit(x, y, dimension)
        embeddings += text -> vector.toList.map(_.toDouble)
        val checksum = new java.util.zip.Adler32()
        checksum.update(UTF8.bytes(source))
        // Local sources: the file of the document, relative to $AFP, holds its source two lines
        // below the indexed start line.
        val file = sources.map { dir =>
          val name = e + "/" + kind.name + ".thy"
          val theory = Isabelle_System.make_directory(dir + Path.basic(e)) +
            Path.basic(kind.name).thy
          File.write(theory, "theory T imports Main begin\n\n" + "\n" * i + source + "\n\nend\n")
          "file" -> ("AFP/" + name)
        }
        val record = Map(
          "id" -> id, "src" -> source, "entity_kname" -> ("T.x" + i + "|thm"), "entry" -> e,
          "entry_date" -> "2026-01-01", "command" -> command, "session" -> e,
          "start_line" -> (i + 1), "consts" -> List("T.shared"), "typs" -> Nil,
          "kind" -> kind.name, "checksum" -> checksum.getValue, "llm_description" -> description,
          "embedding_input" -> text,
          "description_artifact" -> Map(
            "llm_description" -> (Prompt.Begin + description + Prompt.End),
            "zlib.adler32_checksum" -> checksum.getValue)) ++ file
        (record, vector)
      }
      File.write(directory + Path.basic(Index_Format.documents),
        documents.map(d => JSON.Format(d._1)).mkString("", "\n", "\n"))
      // The stub embeds unknown inputs, such as the reference queries, as the first axis.
      val reference_embeddings =
        if (!references) Map.empty
        else Map(Index_Format.references ->
          Index.reference_inputs(fixture_prompts, kind).map(input =>
            Map("input" -> input, "vector" -> unit(1.0, 0.0, dimension).toList.map(_.toDouble))))
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
          .toMap) ++ reference_embeddings
    }
    write(exported + Path.basic(Index_Format.manifest),
      Map("format" -> Index_Format.name, "version" -> Index_Format.version, "corpora" -> corpora))
    (exported, embeddings)
  }

  def unit(x: Double, y: Double, dimension: Int): Array[Float] =
    (x :: y :: List.fill(dimension - 2)(0.0)).map(_.toFloat).toArray

  def csv(path: Path, header: List[String], rows: List[Map[String, String]]): Unit = {
    def field(s: String): String = "\"" + s.replace("\"", "\"\"") + "\""
    File.write(path, (header :: rows.map(r => header.map(r.getOrElse(_, ""))))
      .map(_.map(field).mkString(",")).mkString("", "\r\n", "\r\n"))
  }


  /** API and benchmark **/

  def api_and_benchmark(progress: Progress): Unit =
    Isabelle_System.with_tmp_dir("isasearch-test") { root =>
      val env = new Environment(root)
      val (plain, vectors) = fixture(root + Path.basic("plain"), references = true,
        sources = Some(root + Path.basic("sources")))
      val (metadata, _) = fixture(root + Path.basic("metadata"), metadata = true)
      val (l2, _) = fixture(root + Path.basic("l2"), metric = Distance_Metric.Squared_Euclidean)
      val (large, _) = fixture(root + Path.basic("large"), dimension = 2048, long_source = true)
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
          "openai_embedding_api_key_env" -> "ISASEARCH_TEST_KEY",
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
        // The recorded reference queries are embedded again, not the documents.
        val embedded = stub.calls.collect {
          case (path, body) if path.endsWith("embeddings") => strings(body, "input") }.flatten
        check(embedded.contains("every natural number greater than one has a prime factor") &&
          !embedded.exists(_.startsWith("Commutativity")), "reference embeddings checked")
        check(stub.completions(health = true).isEmpty, "search without LLM")
        env.run("search", search("-r", "commutativity"), ok = false)
        http_api(env, stub, config_path, plain)

        progress.echo("Local embedding and query servers ...")
        llama_servers(env, stub, root, config)

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

        progress.echo("Exports and pruning ...")
        val exports = (root + Path.basic("exports")).implode
        val exported = Path.explode(env.run("export",
          List("-F", "interchange", "-i", "plain", "-D", exports)).out_lines.last)
        for (kind <- Index.kinds) {
          def data(dir: Path, file: String): Path = dir + Path.basic(kind.name) + Path.basic(file)
          def records(dir: Path): List[JSON.T] =
            split_lines(File.read(data(dir, Index_Format.documents))).filter(_.nonEmpty)
              .map(JSON.parse(_))
          check(Bytes.read(data(exported, Index_Format.vectors)) ==
            Bytes.read(data(plain, Index_Format.vectors)), "exported vectors: " + kind)
          check(records(exported).size == records(plain).size &&
            records(exported).zip(records(plain)).forall(same), "exported records: " + kind)
        }
        env.run("export", List("-F", "interchange", "-i", "plain", "-D", exports), ok = false)
        env.run("import", List("-f", exported.implode, "-i", "reimported"))
        env.run("search", List("-c", config_path.implode, "-i", "reimported", "commutativity"))

        // A shipped generation is checked and moved into place as it is.
        def ship(name: String): Path = {
          val target = root + Path.basic("shipped-" + name)
          Path.explode(env.run("export", List("-i", "plain", "-D", target.implode)).out_lines.last)
        }
        val shipped = ship("ok")
        val shipped_manifest = read(shipped + Path.basic(Index_Format.manifest))
        check(str(object_at(shipped_manifest, Index_Format.generation), "lucene").nonEmpty,
          "Lucene version of a shipped generation")
        env.run("import", List("-f", shipped.implode, "-i", "shipped"))
        check(!shipped.is_dir, "shipped generation moved into place")
        check(env.json(env.run("search", List("-c", config_path.implode, "-i", "shipped",
          "commutativity"))).contains("results"), "search of a shipped generation")
        val corrupt = ship("corrupt")
        val segment = File.find_files(corrupt, _.file_name.startsWith("segments_")).head
        File.append(segment, "x")
        env.run("import", List("-f", corrupt.implode, "-i", "corrupt"), ok = false)
        env.run("search", search("unaffected by a corrupt export"))
        check(corrupt.is_dir &&
          !(env.user + Path.explode("isasearch/indexes/corrupt/current.json")).is_file,
          "corrupt generation refused and left in place")
        val future = ship("future")
        write(future + Path.basic(Index_Format.manifest), shipped_manifest.updated(
          Index_Format.generation, object_at(shipped_manifest, Index_Format.generation)
            .updated("lucene", "99.0.0")))
        env.run("import", List("-f", future.implode, "-i", "future"), ok = false)
        releases(env, root, ship("release"), config_path, List(component.expand, packaged))
        val generations = env.user + Path.explode("isasearch/indexes/plain")
        def count(): Int = File.read_dir(generations).count(_.startsWith("generation-"))
        env.run("import", List("-f", plain.implode, "-i", "plain"))
        check(count() > 1, "several generations before pruning")
        env.run("prune", List("-i", "plain"))
        check(count() == 1, "one generation after pruning")
        env.run("search", search("pruned"))

        progress.echo("Inference backends and failures ...")
        // Every endpoint gets its own key and no other: without it, the stub refuses.
        for (backend <- List("openai", "ollama", "llamacpp")) {
          configure("llm_backend" -> backend,
            "embedding_backend" -> (if (backend == "ollama") "ollama" else "openai"),
            (backend + "_query_model") -> "fixture",
            "ollama_base_url" -> stub.url, "llamacpp_base_url" -> stub.url)
          if (backend != "openai") env.run("search", search("-r", "commutativity"), ok = false)
          configure((backend + "_api_key_env") -> "ISASEARCH_TEST_KEY")
          env.run("search", search("-r", "commutativity"))
        }
        write(config_path, config - Endpoint.OpenAI_Embedding.key_env)
        env.run("search", search("commutativity"), ok = false)
        configure()
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
        // Only corpus descriptions accept a completion cut off at max_tokens.
        stub.truncate_completion_contains = "truncated query"
        env.run("search", search("-r", "truncated query"), ok = false)
        stub.truncate_completion_contains = ""
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

  // Fake llama-servers record their arguments and wait; the stub answers on their port.
  // A shipped generation, released as admin/update releases it and served by a local stand-in
  // for the GitHub API (option isasearch_releases). The registered components are restored
  // after a registered AFP clone chose a release.
  def releases(env: Environment, root: Path, shipped: Path, config_path: Path,
      registered: List[Path]): Unit = {
    val tar = root + Path.basic("release.tar")
    Isabelle_System.gnutar("-cf " + File.bash_path(tar) + " " + File.bash_path(shipped.base),
      dir = shipped.dir).check
    val packed = Bytes.read(tar)
      .compress(Compress.Options_Zstd(), cache = Compress.Cache.make()).make_array
    val half = packed.length / 2
    val parts = List(packed.take(half), packed.drop(half)).zipWithIndex.map { case (b, i) =>
      ("isasearch-plain-20261109-afp-0726d9f1e0bf.tar.zst.00" + i) -> b
    }
    val sums = parts.map { case (name, b) => hash(b) + "  " + name }.mkString("", "\n", "\n")
    val bad_sums = parts.map { case (name, _) => "0" * 64 + "  " + name }.mkString("", "\n", "\n")

    // An AFP clone of the releases' AFP repository: the revision of a release, an AFP changeset
    // without effect on the index, and a local changeset.
    def commit(hg: Mercurial.Repository, path: String, text: String): String = {
      val file = hg.root + Path.explode(path)
      Isabelle_System.make_directory(file.dir)
      File.write(file, text)
      hg.command("commit", args = "-A -u test -d " + Bash.string("0 0") + " -m " +
        Bash.string(path)).check
      hg.log(rev = ".", template = "{node}")
    }
    val upstream = Mercurial.init_repository(root + Path.basic("afp-upstream"))
    val released = commit(upstream, "etc/settings", "AFP_BASE=\"$COMPONENT\"\n")
    val site = commit(upstream, "web/index.html", "site")
    val afp = root + Path.basic("afp-clone")
    commit(Mercurial.clone_repository(upstream.root.implode, afp), "thys/Local/Local.thy", "local")
    val covering = "index-plain-20261110-afp-" + released.take(12)
    val revisions = Map("repository" -> upstream.root.implode, "revisions" -> Map(
      site -> Map[String, Any]("release" -> covering, "distance" -> 1)))

    val files = (parts ::: List("SHA256SUMS" -> UTF8.bytes(sums),
      "bad/SHA256SUMS" -> UTF8.bytes(bad_sums),
      Release.revisions -> UTF8.bytes(JSON.Format(revisions)))).toMap
    val server =
      HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress, 0), 0).nn
    val url = "http://127.0.0.1:" + server.getAddress.nn.getPort
    def release(tag: String, published: String, assets: List[String]): Obj = Map(
      "tag_name" -> tag, "draft" -> false, "prerelease" -> false,
      "published_at" -> published,
      "assets" -> ((parts.map(_._1) ::: assets).map(name => Map(
        "name" -> name.split('/').last, "size" -> files(name).length.toLong,
        "browser_download_url" -> (url + "/assets/" + name)))))
    val listing = List(
      release(covering, "2026-11-10T00:00:00Z", List("SHA256SUMS", Release.revisions)),
      release("index-plain-20261109-afp-0726d9f1e0bf", "2026-11-09T00:00:00Z",
        List("SHA256SUMS")),
      release("index-plain-20261108-afp-1111111111aa", "2026-11-08T00:00:00Z",
        List("bad/SHA256SUMS")))
    server.createContext("/", { (http: HttpExchange | Null) =>
      val exchange = http.nn
      val uri = exchange.getRequestURI.nn
      val body =
        if (uri.getPath.nn == "/releases")
          Some(UTF8.bytes(JSON.Format(if (uri.getQuery.nn.endsWith("page=1")) listing else Nil)))
        else files.get(uri.getPath.nn.stripPrefix("/assets/"))
      body match {
        case Some(bytes) =>
          exchange.sendResponseHeaders(200, bytes.length.toLong)
          using(exchange.getResponseBody.nn)(_.write(bytes))
        case None => exchange.sendResponseHeaders(404, -1)
      }
      exchange.close()
    })
    server.start()
    try {
      val option = List("-o", "isasearch_releases=" + url + "/releases")
      val unregistered = env.run("import", option ::: List("-i", "released"), ok = false)
      check(unregistered.err.contains("No registered AFP") &&
        unregistered.err.contains("-R TAG"), "release without AFP and terminal:\n" +
        unregistered.err)
      env.run("import", option ::: List("-R", "index-plain-20261108-afp-1111111111aa",
        "-i", "released"), ok = false)
      val downloads = env.user + Path.explode("isasearch/downloads")
      check(!(downloads + Path.explode("index-plain-20261108-afp-1111111111aa/" +
        parts.head._1)).is_file, "part with a bad checksum discarded")
      env.run("import", option ::: List("-R", "index-plain-20261109-afp-0726d9f1e0bf",
        "-i", "released"))
      check(!(downloads + Path.basic("index-plain-20261109-afp-0726d9f1e0bf")).is_dir,
        "downloaded parts removed after the import")
      env.run("search", List("-c", config_path.implode, "-i", "released", "commutativity"))

      // The clone gets the release of its newest covered ancestor, with a warning.
      env.register((registered :+ afp)*)
      val chosen = env.run("import", option ::: List("-i", "covered"))
      val output = cat_lines(chosen.out_lines ::: chosen.err_lines)
      check(output.contains("Release for the registered AFP: " + covering) &&
        output.contains("1 AFP changeset since the release, without effect on the index") &&
        output.contains("1 local changeset not in the AFP repository") &&
        output.contains("Not in the index: the changes to Local") &&
        !output.contains("did not answer"),
        "release of the newest covered ancestor:\n" + output)
      env.run("search", List("-c", config_path.implode, "-i", "covered", "commutativity"))
    }
    finally {
      env.register(registered*)
      server.stop(0)
    }
  }

  def llama_servers(env: Environment, stub: Stub, root: Path, config: Obj): Unit = {
    def executable(name: String, script: String): Path = {
      val path = root + Path.basic(name)
      File.write(path, "#!/usr/bin/env bash\n" + script)
      File.set_executable(path)
      path
    }
    def fake(role: String): (Path, Path, Path) = {
      val arguments = root + Path.basic(role + "-server.args")
      val pid = root + Path.basic(role + "-server.pid")
      val path = executable(role + "-server", "printf '%s\\n' \"$@\" > " +
        File.bash_path(arguments) + "\necho $$ > " + File.bash_path(pid) + "\nexec sleep 300\n")
      (path, arguments, pid)
    }
    def lines(path: Path): List[String] = split_lines(File.read(path)).filter(_.nonEmpty)
    def stopped(pid: Path): Boolean = {
      val handle = ProcessHandle.of(Value.Long.parse(Library.trim_line(File.read(pid)))).nn
      !handle.isPresent || !handle.get.nn.isAlive
    }
    val (embedder, embedder_args, embedder_pid) = fake("embedding")
    val failing = executable("failing-server", "echo 'cannot load model' >&2\nexit 3\n")
    val server: Obj = Map("executable" -> embedder.implode, "hf_repo" -> "test/fixture-GGUF:Q8_0",
      "pooling" -> "last", "port" -> stub.port, "arguments" -> List("-t", "2"))
    val config_path = root + Path.basic("llama-servers.json")
    // A started server replaces an endpoint and gets no API key: the stub in its place accepts
    // requests without a key only.
    def replaced(config: Obj, endpoint: Endpoint): Obj =
      config -- (endpoint.url :: endpoint.key_settings)
    val local = replaced(config, Endpoint.OpenAI_Embedding)
    def search(server: Obj, base: Obj = local, ok: Boolean = true, args: List[String] = Nil)
        : Process_Result = {
      write(config_path, base ++ Map(Llama_Server.Role.Embedding.key -> server))
      env.run("search",
        List("-c", config_path.implode, "-i", "plain") ::: args ::: List("commutativity"), ok = ok)
    }

    stub.key = ""
    stub.health_failures = 2
    check(env.json(search(server)).contains("results"), "search through embedding server")
    check(stub.health_failures == 0, "embedding server awaited")
    val args = lines(embedder_args)
    check(List(List("-hf", "test/fixture-GGUF:Q8_0"), List("--alias", "fixture"),
        List("--port", stub.port.toString), List("-np", "1"), List("--pooling", "last"))
        .forall(args.containsSlice(_)) && args.contains("--embedding") &&
        args.takeRight(2) == List("-t", "2"),
      "llama-server arguments: " + args.mkString(" "))
    check(stopped(embedder_pid), "embedding server stopped")

    // On a free port, so that only the exit of the server ends its startup.
    val failure =
      search(server ++ Map("executable" -> failing.implode, "port" -> 0), ok = false)
    check(cat_lines(failure.out_lines ::: failure.err_lines).contains("cannot load model"),
      "embedding server startup failure")
    search(server.removed("hf_repo"), ok = false)
    search(server, base = config, ok = false)
    check(cat_lines(search(server, base = config.removed(Endpoint.OpenAI_Embedding.url),
      ok = false).err_lines).contains("takes no API key"), "key of a replaced endpoint refused")
    // A disabled server is not started: the configured endpoint serves instead, with its key.
    Isabelle_System.rm_tree(embedder_args)
    stub.key = "test-key"
    search(server ++ Map("enabled" -> false), base = config)
    check(!embedder_args.is_file, "disabled embedding server")
    stub.key = ""

    // The query server starts with the first expanded query only, and replaces openai_base_url.
    // A stub of its own reports it ready once the fake has recorded its arguments.
    val (expander, expander_args, expander_pid) = fake("query")
    val query_stub = new Stub(Map.empty)
    query_stub.key = ""
    query_stub.ready = () => expander_args.is_file
    val query_server: Obj = Map("executable" -> expander.implode,
      "hf_repo" -> "test/expander-GGUF:Q4_K_M", "port" -> query_stub.port, "context" -> 2048)
    val expanding = replaced(local, Endpoint.OpenAI) ++
      Map("llm_backend" -> "openai", "openai_query_model" -> "expander",
        Llama_Server.Role.Query.key -> query_server)
    search(server, base = expanding)
    check(!expander_args.is_file, "query server not started without expansion")
    check(env.json(search(server, base = expanding, args = List("-r")))
      .get("refined_query").exists(_ != null), "expanded search through query server")
    val query_args = lines(expander_args)
    check(List(List("-hf", "test/expander-GGUF:Q4_K_M"), List("--alias", "expander"),
        List("-c", "2048"), List("-np", "1")).forall(query_args.containsSlice(_)) &&
        query_args.contains("--no-mmproj") && !query_args.contains("--embedding"),
      "query server arguments: " + query_args.mkString(" "))
    check(stopped(expander_pid), "query server stopped")
    val disabled = expanding.updated(Llama_Server.Role.Query.key,
      query_server.updated("enabled", false))
    search(server, base = disabled, args = List("-r"), ok = false)
    search(server, base = expanding.updated("llm_backend", "ollama"), args = List("-r"),
      ok = false)
    check(query_stub.completions().nonEmpty, "expansion by the query server")
    query_stub.close()
    stub.key = "test-key"
  }

  // The URL that a started server reports.
  def api_url(server: Bash.Process): String = {
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

  def http_api(env: Environment, stub: Stub, config_path: Path, plain: Path): Unit = {
    val server = env.process("server", List("-c", config_path.implode, "-i", "plain", "-p", "0"))
    try {
      val api = api_url(server)
      val client = HttpClient.newHttpClient().nn

      // The status of a POST request to a server, with or without the header of the website.
      def post(base: String, request: String, header: Boolean): Int = {
        val builder = HttpRequest.newBuilder(URI.create(base + request)).nn
        if (header) builder.header(Search.post_header, "open")
        client.send(builder.POST(HttpRequest.BodyPublishers.noBody()).nn.build(),
          HttpResponse.BodyHandlers.ofString()).nn.statusCode()
      }

      def get(request: String): (Int, Obj) = {
        val response = client.send(
          HttpRequest.newBuilder(URI.create(api + request)).nn.GET().nn.build(),
          HttpResponse.BodyHandlers.ofString()).nn
        (response.statusCode(), obj(JSON.parse(response.body().nn)))
      }

      def fetch(request: String): (Int, String, String) = {
        val response = client.send(
          HttpRequest.newBuilder(URI.create(api + request)).nn.GET().nn.build(),
          HttpResponse.BodyHandlers.ofString()).nn
        val content_type = response.headers().nn.firstValue("Content-Type").nn.orElse("").nn
        (response.statusCode(), content_type, response.body().nn)
      }

      // The status of a request that names a server by a host, as a page of that host would.
      def status(base: String, host: String): Int = {
        val uri = URI.create(base).nn
        using(new java.net.Socket(uri.getHost, uri.getPort)) { socket =>
          socket.getOutputStream.nn.write(UTF8.bytes(
            "GET /capabilities HTTP/1.1\r\nHost: " + host + "\r\nConnection: close\r\n\r\n"))
          val reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(socket.getInputStream, UTF8.charset))
          val line = proper_value(reader.readLine()).getOrElse(error("No HTTP response"))
          Value.Int.parse(space_explode(' ', line)(1))
        }
      }

      val (page_code, page_type, page) = fetch("/")
      check(page_code == 200 && page_type.startsWith("text/html") && page.contains("<title>"),
        "website page")
      val katex_css = "vendor/latex.js/css/katex.css"
      val assets =
        """(?:src|href)="(vendor/[^"]+)"""".r.findAllMatchIn(page).map(_.group(1)).toList :::
          """url\('\.\./(fonts/[^']+)'\)""".r.findAllMatchIn(fetch("/" + katex_css)._3)
            .map("vendor/latex.js/" + _.group(1)).toList
      check(assets.contains(katex_css) && assets.exists(_.endsWith(".woff2")), "website assets")
      for (asset <- assets) check(fetch("/" + asset)._1 == 200, "website asset " + asset)
      check(fetch("/vendor/bootstrap/bootstrap.bundle.min.js")._2.startsWith("text/javascript"),
        "script type")
      for (missing <- List("/missing.html", "/%2e%2e/etc/build.props"))
        check(fetch(missing)._1 == 404, "no website file " + missing)

      val (_, capabilities) = get("/capabilities")
      check(bool(capabilities, "embedding_available") && !bool(capabilities, "query_expansion"),
        "capabilities")
      for ((query, status) <- List(("?query=test&refine_query=true", 503), ("?query=", 400),
          ("?query=test&kind=bad", 400)))
        check(get("/search" + query)._1 == status, "HTTP status for " + query)
      val (code, found) = get("/search?query=test")
      check(code == 200 && list(found("results")).size == 3, "search over HTTP")

      // Results name the local file of a document and the line of its source there, beside
      // the online links; the website shows that file.
      val hits = list(found("results")).map(obj)
      check(hits.forall(h => str(h, "local_file").endsWith("/theorems.thy") &&
        num(h, "local_line", 0) == num(h, "start_line", 0) + 2), "local sources")
      val hit = hits.head
      val (source_code, source_type, source_page) = fetch("/source?kind=theorems&id=" +
        java.net.URLEncoder.encode(str(hit, "id"), "UTF-8"))
      check(source_code == 200 && source_type.startsWith("text/html") &&
        source_page.contains("<span id=\"L" + num(hit, "local_line", 0).toInt + "\" class=\"m\">"),
        "local source page")
      check(fetch("/source?kind=theorems&id=missing")._1 == 404, "no page for unknown documents")

      // The server follows the index to a newly published generation.
      val served = str(capabilities, "generation")
      env.run("import", List("-f", plain.implode, "-i", "plain"))
      val (_, followed) = get("/capabilities")
      check(str(followed, "generation").startsWith("generation-") &&
        str(followed, "generation") != served, "server follows a new generation")
      env.run("prune", List("-i", "plain"))
      check(get("/search?query=pruned")._1 == 200, "search after pruning the old generation")

      // The server answers requests that name it as this machine does, not those of a page of
      // another host whose name leads here.
      for (host <- List("localhost", "127.0.0.1:" + URI.create(api).nn.getPort))
        check(status(api, host) == 200, "request to " + host)
      check(status(api, "attacker.example") == 403, "request to a foreign host")

      // Requests are handled concurrently: the page is served while a search waits for its
      // embedding. That search fails for its input, which leaves the service available.
      stub.fail_input_contains = "refused input"
      val refused = Future.thread("search") { get("/search?query=refused+input")._1 }
      Time.seconds(0.5).sleep()
      check(fetch("/")._1 == 200 && !refused.is_finished, "concurrent requests")
      check(refused.join == 503, "search with a refused input")
      check(get("/search?query=test")._1 == 200, "search after a failed request")
      stub.fail_input_contains = ""

      stub.mode = "dimension"
      check(get("/search?query=unavailable")._1 == 503, "unavailable embedding service")
      check(!bool(get("/capabilities")._2, "embedding_available"), "refreshed capabilities")
      stub.mode = "ok"

      // Both editors are enabled by default. An editor opens only what a POST with the
      // website's header asks for; no editor is started here.
      check(list(get("/capabilities")._2.getOrElse("editors", Nil)).map(e => str(obj(e), "name"))
        == List("jedit", "vscode"), "editors by default")
      val request = "/open?editor=vscode&kind=theorems&id=" +
        java.net.URLEncoder.encode(str(hit, "id"), "UTF-8")
      check(post(api, request, header = false) == 403, "open without the header")
      check(post(api, request.replace("editor=vscode", "editor=emacs").nn, header = true) == 400,
        "open in an unknown editor")
      check(get(request)._1 == 405, "open by GET")
      // A server for other machines turns editors off and names the host of its proxy.
      val shared = env.process("server",
        List("-c", config_path.implode, "-i", "plain", "-o", "isasearch_editors=",
          "-o", "isasearch_hosts=search.example.org", "-p", "0"))
      try {
        val shared_api = api_url(shared)
        check(status(shared_api, "search.example.org") == 200 &&
          status(shared_api, "attacker.example") == 403, "hosts of a shared server")
        val editors = list(obj(JSON.parse(client.send(
          HttpRequest.newBuilder(URI.create(shared_api + "/capabilities")).nn.GET().nn.build(),
          HttpResponse.BodyHandlers.ofString()).nn.body().nn)).getOrElse("editors", Nil))
        check(editors.isEmpty, "no editors when turned off")
        check(post(shared_api, request, header = true) != 200, "no open service without editors")
      }
      finally { shared.terminate() }
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

    val report_path = analysis(root + Path.basic("reports"), "-k", "all", "-x", "-e", "Missing")
    val report = read(report_path)
    check(bool(report, "llm_judge"), "judged duplicates")
    check(same(report("entries"), List("A")) && same(report("missing_entries"), List("Missing")),
      "entry missing from the index reported")
    val summary = report_path.dir + Path.basic(report_path.drop_ext.file_name + "_summary.md")
    val summary_text = File.read(summary)
    check(summary_text == Duplicate_Report.summary(report) &&
      summary_text.contains("| A | definitions |") &&
      summary_text.contains("Not in the index, e.g. because a session failed to build: Missing."),
      "summary view:\n" + summary_text)
    env.run("duplicates", List("-c", config_path.implode, "-i", "plain", "-e", "Missing",
      "-D", (root + Path.basic("missing")).implode), ok = false)
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

    // A judgement cut off at max_tokens counts if its verdict is complete, without another
    // request, and is a failure otherwise.
    configure(List("enable_llm_output_cache" -> false))
    stub.truncate_completion_contains = "Compare "
    val before_cut = stub.calls.size
    val cut = first_candidates(object_at(object_at(
      read(analysis(root + Path.basic("truncated-judge"))), "sections"), "definitions")).head
    check(str(cut, "verdict") == "DUPLICATE" && bool(cut, "judge_truncated") &&
      !cut.contains("judge_error"), "truncated judgement with a verdict")
    check(stub.completions(since = before_cut).count(b =>
      stub.prompt(b).startsWith("Compare ")) == 1, "truncated judgement with a verdict kept")
    val judge_answer = stub.completion_text
    stub.completion_text = Prompt.Begin + "Both items"
    val no_verdict = object_at(object_at(
      read(analysis(root + Path.basic("truncated-no-verdict"))), "sections"), "definitions")
    check(num(object_at(no_verdict, "aggregates"), "judge_failures", 0) == 1 &&
      str(first_candidates(no_verdict).head, "judge_error").startsWith("Truncated"),
      "truncated judgement without a verdict")
    stub.completion_text = judge_answer
    stub.truncate_completion_contains = ""
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
          "openai_embedding_api_key_env" -> "ISASEARCH_TEST_KEY",
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

        val results = found()
        check(results.size == 2 && results.forall(d => str(d, "entry") == "Example-Submission"),
          "searchable entry")
        check(list(manifest("afp-test")("corpora")).map(obj).forall(corpus =>
          list(corpus.getOrElse(Index_Format.references, Nil)).map(obj).map(r => str(r, "input")) ==
            Index.reference_inputs(object_at(object_at(corpus, "recipe"), "prompts"),
              Corpus_Kind.parse(str(corpus, "kind")))), "reference embeddings recorded")
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

        // A description cut off at max_tokens on every attempt is kept and reported, and a
        // document whose description fails is left out until the next build.
        val truncation = Isabelle_System.make_directory(copied + Path.explode("thys/Truncation"))
        File.write(truncation + Path.basic("ROOT"),
          "chapter AFP\n\nsession Truncation = HOL +\n  theories Truncation\n")
        def truncation_theory(lemmas: String*): Unit =
          File.write(truncation + Path.basic("Truncation.thy"),
            "theory Truncation imports Main begin\n" +
              lemmas.map(name => "lemma " + name + ": \"True\" by simp\n").mkString + "end\n")
        truncation_theory("truncated_fact", "refused_fact")
        File.write(copied + Path.explode("thys/ROOTS"), "Example-Submission\nFailing\nTruncation\n")
        def theorems(): Obj =
          list(manifest("afp-truncation")("corpora")).map(obj)
            .find(corpus => str(corpus, "kind") == "theorems").getOrElse(error("No theorems"))
        stub.truncate_completion_contains = "truncated_fact"
        stub.fail_completion_contains = "refused_fact"
        val partial_description = output(run("index", List("Truncation"), index = "afp-truncation"))
        check(partial_description.contains("Truncated description of") &&
          partial_description.contains("Not described") &&
          partial_description.contains("1 truncated, 1 not described"),
          "truncated and undescribed documents reported")
        check(num(theorems(), "count", 0) == 1 &&
          strings(theorems(), "truncated_descriptions").size == 1 &&
          strings(theorems(), "undescribed_documents").size == 1,
          "truncated and undescribed documents recorded")
        stub.fail_completion_contains = ""
        run("index", List("Truncation"), index = "afp-truncation")
        check(num(theorems(), "count", 0) == 2 &&
          strings(theorems(), "truncated_descriptions").size == 1 &&
          strings(theorems(), "undescribed_documents").isEmpty,
          "undescribed document described by the next build, truncated description kept")
        // A batch without any description stops the build: the server does not answer.
        truncation_theory("unanswered_fact")
        stub.fail_completion_contains = "unanswered_fact"
        check(errors(run("index", List("Truncation"), ok = false, index = "afp-truncation"))
          .contains("No document of a batch described"), "batch without descriptions")
        stub.fail_completion_contains = ""
        stub.truncate_completion_contains = ""

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
