/*  Title:      IsaSearch/isabelle/src/search.scala

Semantic search and the HTTP API.
*/

package isabelle.isasearch


import isabelle._

import java.net.URLDecoder
import com.sun.net.httpserver.{HttpExchange, HttpHandler}


object Search {
  import Data._


  /** request errors **/

  case class Unavailable(message: String) extends RuntimeException(message)

  case class Bad_Request(message: String) extends RuntimeException(message)


  /** search service **/

  class Engine(val snapshot: Index.Snapshot, val config: Config) {
    val inference = new Inference.Client(config)


    /* capabilities */

    @volatile private var embedding_error = "Embedding service has not been checked"
    @volatile private var query_error = "Query expansion is not configured"
    @volatile private var checked = 0L

    def refresh(force: Boolean = false): Unit = synchronized {
      if (force || System.currentTimeMillis() - checked >
          config.positive("capability_refresh_seconds", 30).toLong * 1000) {
        try {
          snapshot.corpora.values.foreach(inference.validate_reference)
          embedding_error = ""
        }
        catch {
          case exn: Inference.Failure => embedding_error = exn.getMessage
          case ERROR(msg) => embedding_error = msg
        }
        if (!inference.configured(Model_Role.Query))
          query_error = "Query expansion is not configured"
        else
          try {
            inference.generate("Reply with OK.", health = true)
            query_error = ""
          }
          catch {
            case exn: Inference.Failure => query_error = exn.getMessage
            case ERROR(msg) => query_error = msg
          }
        checked = System.currentTimeMillis()
      }
    }

    def capabilities: Obj = {
      refresh()
      Map(
        "definition_search" -> snapshot.corpora.contains(Corpus_Kind.Definitions),
        "corpora" -> snapshot.corpora.keys.toList.map(_.name).sorted,
        "embedding_available" -> embedding_error.isEmpty,
        "embedding_error" -> embedding_error,
        "query_expansion" -> query_error.isEmpty,
        "query_expansion_error" -> query_error
      )
    }

    def ready(expansion: Boolean): Unit = {
      refresh()
      if (embedding_error.nonEmpty) throw Unavailable(embedding_error)
      if (expansion && query_error.nonEmpty) throw Unavailable(query_error)
    }


    /* query execution */

    def search(
      query: String,
      kind: Corpus_Kind = Corpus_Kind.Theorems,
      mode: Query_Mode = Query_Mode.Original,
      limit: Int = 100
    ): Obj = {
      if (query.trim.isEmpty) throw Bad_Request("query must not be empty")
      if (limit < 1 || limit > 1000) throw Bad_Request("limit must be between 1 and 1000")
      if (!snapshot.corpora.contains(kind)) throw Unavailable("Corpus unavailable: " + kind)
      ready(mode.expands)
      val start = System.nanoTime()
      val corpus = snapshot(kind)
      val completion =
        if (!mode.expands) None
        else {
          val prompt =
            template(Index.prompt(corpus.spec, Prompt.Expand), Map("search_query" -> query))
          try { Some(inference.generate(prompt)) }
          catch {
            case exn: Inference.Failure =>
              query_error = exn.getMessage
              throw Unavailable(query_error)
            case ERROR(msg) =>
              query_error = msg
              throw Unavailable(msg)
          }
        }
      val refined = completion.map(c => marked(c.text))
      val text = refined.map(r => mode.combine(query, r)).getOrElse(query)
      val input = template(Index.prompt(corpus.spec, Prompt.Retrieve), Map("search_query" -> text))
      val vector = try { inference.embed(List(input), corpus.spec).head }
      catch {
        case exn: Inference.Failure =>
          embedding_error = exn.getMessage
          throw Unavailable(embedding_error)
        case ERROR(msg) =>
          embedding_error = msg
          throw Unavailable(msg)
      }
      val results = corpus
        .search(vector, limit)
        .map(_.removed("embedding_input").removed("description_artifact"))
      val elapsed = (System.nanoTime() - start) / 1e9
      val legacy = completion.filter(_.cached).map(c => elapsed + c.duration).getOrElse(elapsed)
      Map(
        "results" -> results,
        "duration" -> legacy,
        "elapsed_duration" -> elapsed,
        "cache_hit" -> completion.exists(_.cached),
        "refined_query" -> refined.orNull
      )
    }
  }


  /** HTTP requests **/

  def parameters(raw: String): Map[String, String] = {
    if (raw == null || raw.isEmpty) Map.empty
    else
      raw
        .split("&")
        .map { field =>
          val parts = field.split("=", 2)

          def decode(s: String) = URLDecoder.decode(s, "UTF-8")
          decode(parts(0)) -> decode(parts.lift(1).getOrElse(""))
        }
        .toMap
  }

  def boolean(s: String): Boolean = s.toLowerCase match {
    case "true" => true
    case "false" => false
    case _ => throw Bad_Request("refine_query must be true or false")
  }


  /** HTTP services **/

  def service(name: String)(action: Map[String, String] => Obj): HTTP.Service =
    new HTTP.Service(name) {
      def apply(request: HTTP.Request): Option[HTTP.Response] = None

      override def handler(server_name: String): HttpHandler = (exchange: HttpExchange) => {
        def respond(code: Int, body: Obj): Unit =
          HTTP
            .Response(Bytes(JSON.Format(body)), "application/json; charset=utf-8")
            .write(exchange, code)
        try {
          if (exchange.getRequestURI.getPath != "/" + this.name)
            respond(404, Map("error" -> "Unknown endpoint"))
          else if (exchange.getRequestMethod != "GET") respond(405, Map("error" -> "Use GET"))
          else respond(200, action(parameters(exchange.getRequestURI.getRawQuery)))
        }
        catch {
          case exn: Bad_Request => respond(400, Map("error" -> exn.getMessage))
          case exn: IllegalArgumentException =>
            respond(400, Map("error" -> "Invalid request parameter"))
          case exn: Unavailable => respond(503, Map("error" -> exn.getMessage))
          case exn: Inference.Failure => respond(503, Map("error" -> exn.getMessage))
          case ERROR(msg) => respond(500, Map("error" -> msg))
          case scala.util.control.NonFatal(_) =>
            respond(500, Map("error" -> "Internal server error"))
        }
        finally { exchange.close() }
      }
    }

  def server(engine: Engine, port: Int): HTTP.Server = HTTP.server(
    port,
    name = "",
    services = List(
      service("capabilities")(_ => engine.capabilities),
      service("search") { args =>
        engine.search(
          args.getOrElse("query", ""),
          kind = try { Corpus_Kind.parse(args.getOrElse("kind", Corpus_Kind.Theorems.name)) }
          catch { case ERROR(msg) => throw Bad_Request(msg) },
          mode =
            if (boolean(args.getOrElse("refine_query", "false"))) Query_Mode.Combined
            else Query_Mode.Original,
          limit = args.getOrElse("limit", "100").toInt
        )
      }
    )
  )
}
