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

  // User errors: their message is reported without the exception class.
  case class Unavailable(override val message: String) extends Exn.User_Error(message)

  case class Bad_Request(override val message: String) extends Exn.User_Error(message)


  /** local sources **/

  // FindFacts names the file of a document relative to an Isabelle variable, without its '$'
  // (e.g. AFP/Entry/T.thy for $AFP, ISABELLE_HOME/src/HOL/...). Where the variable is set on
  // this machine and the file exists, a result names the local file and the line of the
  // document's source there; the local file may be another version than the indexed one, and
  // without the source in it the line is left out.
  object Local_Sources {
    def file(record: Obj): Option[Path] = {
      val name = str(record, "file")
      val variable = name.takeWhile(_ != '/')
      if (!variable.matches("[A-Za-z_][A-Za-z0-9_]*") || name.length <= variable.length + 1 ||
          Isabelle_System.getenv(variable).isEmpty) None
      else
        try { Some(Path.explode("$" + name).expand).filter(_.is_file) }
        catch { case ERROR(_) => None }
    }

    // The line of the occurrence of the source nearest to the indexed start line.
    def line(text: String, record: Obj): Option[Int] = {
      val src = str(record, "src")
      val start = num(record, "start_line", 0).toInt
      if (src.isEmpty) None
      else
        Iterator.iterate(text.indexOf(src))(i => text.indexOf(src, i + 1))
          .takeWhile(_ >= 0)
          .map(i => text.take(i).count(_ == '\n') + 1)
          .minByOption((n: Int) => (math.abs(n - start), n))
    }

    // Theory text with symbols decoded and Unix line ends, as in the sources of the index.
    def text(path: Path): String = Symbol.decode(File.read(path)).replace("\r\n", "\n").nn

    def apply(records: List[Obj]): List[Obj] = {
      val texts = scala.collection.mutable.Map.empty[Path, String]
      records.map { record =>
        file(record) match {
          case None => record
          case Some(path) =>
            val found = line(texts.getOrElseUpdate(path, text(path)), record)
            record ++ Map("local_file" -> File.platform_path(path)) ++
              found.map("local_line" -> _)
        }
      }
    }
  }


  /** statements **/

  // Hits with the same statement (Text_Preparation.statement), e.g. of a theory that an AFP
  // entry copies or of a fact restated under another name, as one result: ranked by its nearest
  // copy, represented by a copy of the distribution if there is one, the others under "copies".
  // Copies are those among the hits up to the last result.
  def collapse(ranked: Iterator[Obj], limit: Int): List[Obj] = {
    val groups = scala.collection.mutable.LinkedHashMap.empty[String, List[Obj]]
    var more = true
    while (more && ranked.hasNext) {
      val record = ranked.next()
      val key = Text_Preparation.statement(str(record, "src"))
      if (groups.contains(key)) groups(key) = groups(key) :+ record
      else if (groups.size < limit) groups(key) = List(record)
      else more = false
    }
    groups.values.toList.map { copies =>
      val result = copies.find(str(_, "entry").isEmpty).getOrElse(copies.head)
      result.updated("copies", copies.filterNot(_ eq result))
    }
  }

  // The qualifier between the theory and the first name that a command declares, e.g. the locale
  // `gd_term` of `Reduced_GB.gd_term.is_reduced_GB_unique` in theory `Groebner_Bases.Reduced_GB`:
  // usually the locale or class that a fact or constant is stated in, otherwise a name space.
  // The facts that definitions generate (e.g. `deriv.simps`) are qualified by their constant.
  def qualifier(record: Obj): Option[String] = {
    val theory = Long_Name.base_name(str(record, "theory"))
    val declared = strings(record, "consts") ::: strings(record, "typs") match {
      case Nil => strings(record, "thms")
      case names => names
    }
    declared.headOption.flatMap(name => Library.try_unprefix(theory + ".", name))
      .map(Long_Name.qualifier).filter(_.nonEmpty)
  }


  /** search service **/

  // Searches over the snapshots of an index source, with the inference endpoints of the
  // configuration of the servers, which start on first use.
  class Engine(val index: Index.Source, val servers: Llama_Server.Servers) {
    val config: Config = servers.config
    val inference = new Inference.Client(config, servers = Some(servers))

    // Approximate neighbours reranked per search: 500 recover about 99% of the exact top 100.
    val candidates = config.positive("search_candidates", 500)

    def use[A](body: Index.Snapshot => A): A = index.use(body)


    /* capabilities */

    @volatile private var embedding_error = "Embedding service has not been checked"
    @volatile private var query_error = "Query expansion is not configured"
    @volatile private var checked = 0L
    @volatile private var checked_root: Option[Path] = None

    // The embedder is checked against the references of every corpus, again when the snapshot
    // changes. A query server that has not started yet counts as available: it starts with the
    // first expanded query rather than for a check.
    def refresh(snapshot: Index.Snapshot, force: Boolean = false): Unit = synchronized {
      if (force || !checked_root.contains(snapshot.root) || System.currentTimeMillis() - checked >
          config.positive("capability_refresh_seconds", 30).toLong * 1000) {
        try {
          snapshot.corpora.values.foreach(inference.validate_reference)
          embedding_error = ""
        }
        catch {
          case exn: Inference.Failure => embedding_error = exn.message
          case ERROR(msg) => embedding_error = msg
        }
        if (!inference.configured(Model_Role.Query))
          query_error = "Query expansion is not configured"
        else if (servers.waiting(Llama_Server.Role.Query)) query_error = ""
        else
          try {
            inference.generate("Reply with OK.", health = true)
            query_error = ""
          }
          catch {
            case exn: Inference.Failure => query_error = exn.message
            case ERROR(msg) => query_error = msg
          }
        checked = System.currentTimeMillis()
        checked_root = Some(snapshot.root)
      }
    }

    def capabilities: Obj = use { snapshot =>
      refresh(snapshot)
      Map(
        "generation" -> snapshot.root.file_name,
        "definition_search" -> snapshot.corpora.contains(Corpus_Kind.Definitions),
        "corpora" -> snapshot.corpora.keys.toList.map(_.name).sorted,
        "embedding_available" -> embedding_error.isEmpty,
        "embedding_error" -> embedding_error,
        "query_expansion" -> query_error.isEmpty,
        "query_expansion_error" -> query_error
      )
    }

    def ready(snapshot: Index.Snapshot, expansion: Boolean): Unit = {
      refresh(snapshot)
      if (embedding_error.nonEmpty) throw Unavailable(embedding_error)
      if (expansion && query_error.nonEmpty) throw Unavailable(query_error)
    }

    def ready(expansion: Boolean): Unit = use(ready(_, expansion))


    /* query execution */

    def search(
      query: String,
      kind: Corpus_Kind = Corpus_Kind.Theorems,
      mode: Query_Mode = Query_Mode.Original,
      limit: Int = 100,
      filter: Search_Filter = Search_Filter(),
      collapse: Boolean = false
    ): Obj = use(search(_, query, kind, mode, limit, filter, collapse))

    // The nearest documents of the filter, the copies of a statement as one result if
    // `collapse` is set.
    def search(
      snapshot: Index.Snapshot,
      query: String,
      kind: Corpus_Kind,
      mode: Query_Mode,
      limit: Int,
      filter: Search_Filter,
      collapse: Boolean
    ): Obj = {
      if (Library.trim_string(query).isEmpty) throw Bad_Request("query must not be empty")
      if (limit < 1 || limit > 1000) throw Bad_Request("limit must be between 1 and 1000")
      if (!snapshot.corpora.contains(kind)) throw Unavailable("Corpus unavailable: " + kind)
      ready(snapshot, mode.expands)
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
              query_error = exn.message
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
          embedding_error = exn.message
          throw Unavailable(embedding_error)
        case ERROR(msg) =>
          embedding_error = msg
          throw Unavailable(msg)
      }
      val nearest = corpus.ranked(vector, math.max(limit, candidates), filter)
        .filter(filter.admits)
        .map(_.removed("embedding_input").removed("description_artifact"))
      val results =
        if (collapse) Search.collapse(nearest, limit).map(result =>
          result.updated("copies", Local_Sources(list(result("copies")).map(obj))))
        else nearest.take(limit).toList
      val located = Local_Sources(results)
      val elapsed = (System.nanoTime() - start) / 1e9
      val legacy = completion.filter(_.cached).map(c => elapsed + c.duration).getOrElse(elapsed)
      Map(
        "results" -> located,
        "duration" -> legacy,
        "elapsed_duration" -> elapsed,
        "cache_hit" -> completion.exists(_.cached),
        "refined_query" -> refined.orNull
      )
    }
  }


  /** HTTP requests **/

  def parameters(raw: String | Null): Map[String, String] = {
    def decode(s: String): String = URLDecoder.decode(s, "UTF-8").nn

    proper_string(raw) match {
      case None => Map.empty
      case Some(query) =>
        space_explode('&', query).map { field =>
          val i = field.indexOf('=')
          if (i < 0) decode(field) -> ""
          else decode(field.take(i)) -> decode(field.drop(i + 1))
        }.toMap
    }
  }

  def boolean(args: Map[String, String], name: String): Boolean =
    Word.lowercase(args.getOrElse(name, "false")) match {
      case "true" => true
      case "false" => false
      case _ => throw Bad_Request(name + " must be true or false")
    }

  // The filter of a search request: `source` (all, distribution or afp), `entries` and
  // `sessions` (comma separated), `mentions` (separated by spaces).
  def filter(args: Map[String, String]): Search_Filter = {
    def names(name: String, sep: Char): Option[List[String]] =
      args.get(name).map(s => space_explode(sep, s).map(Library.trim_string).filter(_.nonEmpty))
    try {
      Search_Filter(
        source = Search_Source.parse(args.getOrElse("source", Search_Source.All.name)),
        entries = names("entries", ',').map(_.toSet),
        sessions = names("sessions", ',').map(_.toSet),
        mentions = args.get("mentions").toList.flatMap(s =>
          s.split("\\s+").nn.toList.map(_.nn).filter(_.nonEmpty)))
    }
    catch { case ERROR(msg) => throw Bad_Request(msg) }
  }

  // The parameters of a filter, as `filter` reads them.
  def filter_parameters(filter: Search_Filter): List[(String, String)] =
    List("source" -> filter.source.name) :::
    filter.entries.map(es => "entries" -> es.toList.sorted.mkString(",")).toList :::
    filter.sessions.map(ss => "sessions" -> ss.toList.sorted.mkString(",")).toList :::
    (if (filter.mentions.isEmpty) Nil else List("mentions" -> filter.mentions.mkString(" ")))


  /** HTTP services **/

  // A POST service requires the header X-IsaSearch: a page of another origin cannot send it
  // without a CORS preflight, which this server does not answer.
  val post_header = "X-IsaSearch"

  def service(name: String, post: Boolean = false)(action: Map[String, String] => Obj)
      : HTTP.Service =
    new HTTP.Service(name) {
      def apply(request: HTTP.Request): Option[HTTP.Response] = None

      override def handler(server_name: String): HttpHandler = { (http: HttpExchange | Null) =>
        val exchange = http.nn

        def respond(code: Int, body: Obj): Unit =
          HTTP
            .Response(Bytes(JSON.Format(body)), "application/json; charset=utf-8")
            .write(exchange, code)
        try {
          val uri = exchange.getRequestURI.nn
          if (uri.getPath != "/" + this.name)
            respond(404, Map("error" -> "Unknown endpoint"))
          else if (exchange.getRequestMethod != (if (post) "POST" else "GET"))
            respond(405, Map("error" -> ("Use " + (if (post) "POST" else "GET"))))
          else if (post && exchange.getRequestHeaders.nn.getFirst(post_header) == null)
            respond(403, Map("error" -> ("Missing header " + post_header)))
          else respond(200, action(parameters(uri.getRawQuery)))
        }
        catch {
          case exn: Bad_Request => respond(400, Map("error" -> exn.message))
          case exn: IllegalArgumentException =>
            respond(400, Map("error" -> "Invalid request parameter"))
          case exn: Unavailable => respond(503, Map("error" -> exn.message))
          case exn: Inference.Failure => respond(503, Map("error" -> exn.message))
          case ERROR(msg) => respond(500, Map("error" -> msg))
          case scala.util.control.NonFatal(_) =>
            respond(500, Map("error" -> "Internal server error"))
        }
        finally { exchange.close() }
      }
    }

  /** website **/

  // The page and its vendored libraries, read from the component on every request.
  def web_dir: Path = component + Path.basic("web")

  def web_mime_type(file: Path): String =
    file.get_ext match {
      case "html" => HTTP.Content.mime_type_html
      case "css" => HTTP.Content.mime_type_css
      case "js" => HTTP.Content.mime_type_js
      case "woff2" => "font/woff2"
      case _ => HTTP.Content.mime_type_text
    }

  // Bound at the root, the website receives every request the API services do not.
  val website: HTTP.Service =
    new HTTP.Service("") {
      def apply(request: HTTP.Request): Option[HTTP.Response] =
        (if (request.toplevel) Some(Path.basic("index.html")) else request.uri_path)
          .map(web_dir + _)
          .filter(_.is_file)
          .map(file => HTTP.Response(Bytes.read(file), web_mime_type(file)))
    }

  // The local file of a document as a page with line numbers, its source marked; only files
  // of documents of the index are served.
  def source(engine: Engine): HTTP.Service =
    new HTTP.Service("source") {
      def apply(request: HTTP.Request): Option[HTTP.Response] = {
        val args = parameters(request.uri.getRawQuery)
        val kind =
          try { Corpus_Kind.parse(args.getOrElse("kind", Corpus_Kind.Theorems.name)) }
          catch { case ERROR(_) => return None }
        val record = engine.use(snapshot =>
          snapshot.corpora.get(kind).flatMap(_.get(args.getOrElse("id", ""))).map(_._2))
        for { r <- record; path <- Local_Sources.file(r) } yield {
          val text = Local_Sources.text(path)
          val first = Local_Sources.line(text, r).getOrElse(0)
          val last = first + split_lines(str(r, "src")).length - 1
          val lines = split_lines(text).zipWithIndex.map { case (line, i) =>
            val n = i + 1
            "<span id=\"L" + n + "\"" + (if (first <= n && n <= last) " class=\"m\"" else "") +
              "><a href=\"#L" + n + "\">" + n + "</a>" + HTML.output(line) + "</span>"
          }
          HTTP.Response.html(
            "<!DOCTYPE html>\n<html><head><meta charset=\"utf-8\"><title>" +
            HTML.output(str(r, "theory")) + "</title><style>" +
            "body{margin:0;font:14px/1.45 monospace}h1{font:15px sans-serif;margin:12px}" +
            "pre{margin:0}span{display:block;white-space:pre-wrap}" +
            "a{display:inline-block;width:5em;color:#888;text-align:right;margin-right:1em;" +
            "text-decoration:none}.m{background:#fff3b0}</style></head><body><h1>" +
            HTML.output(File.platform_path(path)) + "</h1><pre>" + lines.mkString +
            "</pre></body></html>")
        }
      }
    }

  /** editors **/

  // Opens the local file of a document in an Isabelle editor at the line of its source; a
  // newly started editor outlives this server.
  def open_in_editor(
    engine: Engine,
    editors: List[Isabelle_Editor],
    args: Map[String, String]
  ): Obj = {
    val editor =
      try { Isabelle_Editor.parse(args.getOrElse("editor", "")) }
      catch { case ERROR(msg) => throw Bad_Request(msg) }
    if (!editors.contains(editor)) throw Bad_Request("Editor not enabled: " + editor)
    val kind =
      try { Corpus_Kind.parse(args.getOrElse("kind", Corpus_Kind.Theorems.name)) }
      catch { case ERROR(msg) => throw Bad_Request(msg) }
    val id = args.getOrElse("id", "")
    val record = engine.use(_.corpora.get(kind).flatMap(_.get(id)).map(_._2))
      .getOrElse(throw Bad_Request("Unknown document: " + id))
    val path = Local_Sources.file(record)
      .getOrElse(throw Bad_Request("No local file for " + id))
    val line = Local_Sources.line(Local_Sources.text(path), record)
    val command = editor.command(File.bash_path(Path.explode("$ISABELLE_HOME/bin/isabelle")),
      File.bash_path(path), line)
    Isabelle_System.bash("nohup " + command + " > /dev/null 2>&1 &").check
    Map("editor" -> editor.name, "file" -> File.platform_path(path)) ++ line.map("line" -> _)
  }

  def server(engine: Engine, port: Int, editors: List[Isabelle_Editor] = Nil): HTTP.Server =
    HTTP.server(
      port,
      name = "",
      services = List(
        website,
        source(engine),
        service("capabilities")(_ =>
          engine.capabilities.updated("editors", editors.map(e => Map("name" -> e.name,
            "title" -> e.title)))),
        service("search") { args =>
          engine.search(
            args.getOrElse("query", ""),
            kind = try { Corpus_Kind.parse(args.getOrElse("kind", Corpus_Kind.Theorems.name)) }
            catch { case ERROR(msg) => throw Bad_Request(msg) },
            mode =
              if (boolean(args, "refine_query")) Query_Mode.Combined else Query_Mode.Original,
            limit = args.getOrElse("limit", "100").toInt,
            filter = filter(args),
            collapse = boolean(args, "collapse")
          )
        }
      ) ::: (if (editors.isEmpty) Nil
             else List(service("open", post = true)(open_in_editor(engine, editors, _))))
    )
}
