/*  Title:      IsaSearch/isabelle/src/embedding_server.scala

A llama.cpp embedding server that the searching tools run on this machine.
*/

package isabelle.isasearch


import isabelle._

import java.net.{InetAddress, ServerSocket, URI}
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.time.Duration


object Embedding_Server {
  import Data._


  /** configuration **/

  // A configuration with this object has the searching tools start llama-server on loopback
  // and send their embedding requests there instead of to openai_embedding_base_url.
  val key = "llamacpp_embedding_server"

  def requested(config: Config): Boolean = config.values.contains(key)

  // Paths in the object resolve against the configuration file, like all others.
  private def settings(config: Config): Config =
    Config(object_at(config.values, key), config.base)

  // The server answers under the embedding model name of the configuration, which searches
  // check against the index; it keeps llama.cpp's GPU offload default (all layers, if any).
  def command(config: Config, port: Int): List[String] = {
    val settings = this.settings(config)
    if (config.string("openai_embedding_base_url").nonEmpty)
      error("Configure either openai_embedding_base_url or " + key + ", not both")
    val backend =
      Inference_Backend.parse(config.string("embedding_backend", Inference_Backend.OpenAI.name))
    if (backend != Inference_Backend.OpenAI && backend != Inference_Backend.LlamaCpp)
      error(key + " requires the embedding backend openai, not " + backend)
    val model = config.string("openai_embedding_model", config.string("embedding_model"))
    if (model.isEmpty) error("Configure openai_embedding_model (or embedding_model)")
    val source = (settings.string("hf_repo"), settings.string("model_file")) match {
      case (repo, "") if repo.nonEmpty => List("-hf", repo)
      case ("", file) if file.nonEmpty =>
        val path = settings.path("model_file", "")
        if (!path.is_file) error("Missing model file: " + path.implode)
        List("-m", File.platform_path(path))
      case _ => error(key + " needs exactly one of hf_repo and model_file")
    }
    val context = settings.positive("context", 4096).toString
    val pooling = settings.string("pooling")
    settings.string("executable", "llama-server") :: source :::
      List("--embedding", "--alias", model, "--host", "127.0.0.1", "--port", port.toString,
        "-c", context, "-b", context, "-ub", context, "-np", "1") :::
      (if (pooling.nonEmpty) List("--pooling", pooling) else Nil) :::
      strings(settings.values, "arguments")
  }

  // The first start of an hf_repo model downloads it, which takes most of this time.
  def startup_timeout(config: Config): Time =
    Time.seconds(settings(config).positive("startup_timeout", 1800).toDouble)

  def port(config: Config): Int =
    settings(config).integer("port", 0) match {
      case 0 => using(new ServerSocket(0, 1, InetAddress.getLoopbackAddress))(_.getLocalPort)
      case n => n
    }


  /** process **/

  private val log_date = Date.Format("uuuuMMdd-HHmmss")

  // Runs body with the configuration as it is, or with the embedding endpoint of a server
  // started for its duration.
  def apply[A](config: Config)(body: Config => A): A =
    if (!requested(config)) body(config)
    else using(start(config))(server => body(server.config))

  def start(config: Config): Server = {
    val port = this.port(config)
    val command = this.command(config, port)
    val log = home + Path.explode("logs") +
      Path.basic("llama-server-" + log_date(Date.now()) + ".log")
    Isabelle_System.make_directory(log.dir)
    val download =
      proper_string(settings(config).string("hf_repo"))
        .map(" (its first start downloads " + _ + ")").getOrElse("")
    Output.writeln("Starting " + command.head + download + "; log: " + log.expand.implode)
    val process = Bash.process(
      "exec " + Bash.strings(command) + " > " + File.bash_path(log) + " 2>&1",
      description = "llama-server")
    val exit = Future.thread("llama-server") { process.join() }
    val url = "http://127.0.0.1:" + port
    try {
      val http = HttpClient.newBuilder().nn.connectTimeout(Duration.ofSeconds(5)).nn.build().nn
      val health =
        HttpRequest.newBuilder(URI.create(url + "/health")).nn
          .timeout(Duration.ofSeconds(5)).nn.GET().nn.build().nn
      def ready: Boolean =
        try { http.send(health, HttpResponse.BodyHandlers.discarding()).nn.statusCode() == 200 }
        catch { case _: java.io.IOException => false }
      val deadline = Time.now() + startup_timeout(config)
      while (!ready) {
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
    Output.writeln("Embedding server ready: " + url)
    new Server(process, config.updated("openai_embedding_base_url", url + "/v1"))
  }

  class Server private[Embedding_Server](process: Bash.Process, val config: Config)
      extends AutoCloseable {
    def close(): Unit = process.terminate()
  }
}
