/*  Title:      IsaSearch/isabelle/src/llama_server.scala

llama.cpp servers that the searching tools run on this machine, one per model role.
*/

package isabelle.isasearch


import isabelle._

import java.net.{InetAddress, ServerSocket, URI}
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.time.Duration


object Llama_Server {
  import Data._


  /** roles **/

  // A configuration with the object of a role has the searching tools start llama-server on
  // loopback when the role is first needed, and send its requests there instead of to the
  // endpoint of the role. With "enabled": false the object is kept but nothing is started.
  enum Role(val name: String, val key: String, val endpoint: String) extends Named_Value {
    case Embedding
      extends Role("embedding", "llamacpp_embedding_server", "openai_embedding_base_url")
    case Query extends Role("query", "llamacpp_query_server", "openai_base_url")

    def description: String = name + " server"
  }

  def settings(config: Config, role: Role): Option[Config] =
    if (!config.values.contains(role.key)) None
    else {
      // Paths in the object resolve against the configuration file, like all others.
      val settings = Config(object_at(config.values, role.key), config.base)
      if (settings.boolean("enabled", true)) Some(settings) else None
    }

  def requested(config: Config, role: Role): Boolean = settings(config, role).isDefined

  def roles(config: Config): List[Role] = Role.values.toList.filter(requested(config, _))

  // The server answers under the model name of the configuration: searches check the
  // embedding model against the index, and the query model keys the LLM output cache.
  def model(config: Config, role: Role): String =
    role match {
      case Role.Embedding =>
        config.string("openai_embedding_model", config.string("embedding_model"))
      case Role.Query => config.string("openai_query_model")
    }

  // llama.cpp keeps its GPU offload default (all layers, if any).
  def command(config: Config, role: Role, port: Int): List[String] = {
    val settings = this.settings(config, role).getOrElse(error("No enabled " + role.key))
    if (config.string(role.endpoint).nonEmpty)
      error("Configure either " + role.endpoint + " or " + role.key + ", not both")
    role match {
      case Role.Embedding =>
        val backend = Inference_Backend.parse(
          config.string("embedding_backend", Inference_Backend.OpenAI.name))
        if (backend != Inference_Backend.OpenAI && backend != Inference_Backend.LlamaCpp)
          error(role.key + " requires the embedding backend openai, not " + backend)
      case Role.Query =>
        val backend = Inference_Backend.parse(
          config.string("llm_backend", Inference_Backend.Disabled.name))
        if (backend != Inference_Backend.OpenAI)
          error(role.key + " requires the LLM backend openai, not " + backend)
    }
    val model = this.model(config, role)
    if (model.isEmpty)
      error("Configure " + (if (role == Role.Embedding) "openai_embedding_model" else
        "openai_query_model") + " for " + role.key)
    val source = (settings.string("hf_repo"), settings.string("model_file")) match {
      case (repo, "") if repo.nonEmpty => List("-hf", repo)
      case ("", file) if file.nonEmpty =>
        val path = settings.path("model_file", "")
        if (!path.is_file) error("Missing model file: " + path.implode)
        List("-m", File.platform_path(path))
      case _ => error(role.key + " needs exactly one of hf_repo and model_file")
    }
    val context = settings.positive("context", 4096).toString
    val specific = role match {
      case Role.Embedding =>
        val pooling = settings.string("pooling")
        List("--embedding", "-b", context, "-ub", context) :::
          (if (pooling.nonEmpty) List("--pooling", pooling) else Nil)
      // Expansion is text only: no multimodal projector is downloaded with an hf_repo.
      case Role.Query => List("--no-mmproj")
    }
    settings.string("executable", "llama-server") :: source :::
      List("--alias", model, "--host", "127.0.0.1", "--port", port.toString, "-c", context,
        "-np", "1") ::: specific ::: strings(settings.values, "arguments")
  }

  // The first start of an hf_repo model downloads it, which takes most of this time.
  def startup_timeout(settings: Config): Time =
    Time.seconds(settings.positive("startup_timeout", 1800).toDouble)

  def port(config: Config, role: Role): Int =
    settings(config, role).map(_.integer("port", 0)).getOrElse(0) match {
      case 0 => using(new ServerSocket(0, 1, InetAddress.getLoopbackAddress))(_.getLocalPort)
      case n => n
    }


  /** managed servers **/

  private val log_date = Date.Format("uuuuMMdd-HHmmss")

  // The servers of the requested roles of a configuration. Their ports are fixed up front, so
  // that the configuration of the inference clients is known before any server runs; a server
  // starts on the first request of its role and again if it has stopped.
  class Servers(base: Config) extends AutoCloseable {
    private val managed: Map[Role, Managed] =
      roles(base).map { role =>
        val port = Llama_Server.port(base, role)
        role -> new Managed(role, command(base, role, port), port)
      }.toMap

    val config: Config =
      managed.values.foldLeft(base)((config, m) => config.updated(m.role.endpoint, m.url + "/v1"))

    def requested(role: Role): Boolean = managed.contains(role)

    // A requested server that has not started yet, or has stopped since.
    def waiting(role: Role): Boolean = managed.get(role).exists(!_.running)

    def ensure(role: Role): Unit = managed.get(role).foreach(_.ensure())

    // A signal ends the JVM without closing its resources: the servers stop with it.
    private val shutdown =
      new Thread(new Runnable { def run(): Unit = managed.values.foreach(_.close()) })
    if (managed.nonEmpty) Runtime.getRuntime.nn.addShutdownHook(shutdown)

    def close(): Unit = {
      managed.values.foreach(_.close())
      if (managed.nonEmpty) {
        try { Runtime.getRuntime.nn.removeShutdownHook(shutdown) }
        catch { case _: IllegalStateException => }
      }
    }

    private class Managed(val role: Role, command: List[String], port: Int) {
      val url: String = "http://127.0.0.1:" + port
      private val settings = Llama_Server.settings(base, role).get

      // Read without the lock, which a startup holds for as long as a download takes.
      @volatile private var process: Option[(Bash.Process, Future[Int])] = None
      @volatile private var closed = false

      def running: Boolean = process.exists(!_._2.is_finished)

      def ensure(): Unit = synchronized {
        if (closed) error("The " + role.description + " is closed")
        if (!running) process = Some(start())
      }

      def close(): Unit = {
        closed = true
        synchronized {
          process.foreach(_._1.terminate())
          process = None
        }
      }

      private def start(): (Bash.Process, Future[Int]) = {
        val log = home + Path.explode("logs") +
          Path.basic("llama-server-" + role + "-" + log_date(Date.now()) + ".log")
        Isabelle_System.make_directory(log.dir)
        val download =
          proper_string(settings.string("hf_repo"))
            .map(" (its first start downloads " + _ + ")").getOrElse("")
        Output.writeln("Starting " + command.head + " as " + role.description + download +
          "; log: " + log.expand.implode)
        val process = Bash.process(
          "exec " + Bash.strings(command) + " > " + File.bash_path(log) + " 2>&1",
          description = "llama-server")
        val exit = Future.thread("llama-server") { process.join() }
        try {
          val http = HttpClient.newBuilder().nn.connectTimeout(Duration.ofSeconds(5)).nn.build().nn
          val health =
            HttpRequest.newBuilder(URI.create(url + "/health")).nn
              .timeout(Duration.ofSeconds(5)).nn.GET().nn.build().nn
          def ready: Boolean =
            try { http.send(health, HttpResponse.BodyHandlers.discarding()).nn.statusCode() == 200 }
            catch { case _: java.io.IOException => false }
          val deadline = Time.now() + startup_timeout(settings)
          while (!ready) {
            if (closed) error("The " + role.description + " was closed during startup")
            if (exit.is_finished) {
              val tail = split_lines(File.read(log)).filter(_.nonEmpty).takeRight(20)
              error(cat_lines(
                (command.head + " stopped during startup (return code " + exit.join + ")") :: tail))
            }
            if (Time.now() > deadline)
              error(command.head + " did not become ready in time; see " + log.expand.implode)
            Time.seconds(0.5).sleep()
          }
        }
        catch {
          case exn: Throwable =>
            process.terminate()
            throw exn
        }
        Output.writeln("The " + role.description + " is ready: " + url)
        (process, exit)
      }
    }
  }
}
