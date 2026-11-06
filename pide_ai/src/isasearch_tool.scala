/*  Title:      IsaSearch/pide_ai/src/isasearch_tool.scala

Semantic search of the AFP and the Isabelle distribution as a tool of PIDE AI.
*/

package isabelle.isasearch.pide_ai


import isabelle._
import isabelle.pide.ai.{JSON_Object, JSON_Schema, PIDE_AI_Client_Context, PIDE_AI_Server,
  PIDE_AI_Session, PIDE_AI_Tool, PIDE_AI_Tool_Result, PIDE_AI_Tool_Schema, PIDE_AI_Tools, Task}
import isabelle.isasearch.{Corpus_Kind, Data, Search, Search_Filter, Search_Source,
  Text_Preparation}

import java.net.{URI, URLEncoder}
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.time.Duration


object IsaSearch_Tool {
  import Data._


  /** search server **/

  // The search runs in a server of the IsaSearch component, a process of its own: like the
  // tools of FindFacts, it keeps Solr and Lucene off the classpath of Isabelle's JVM. It
  // serves the default configuration and index of the component (options isasearch_config and
  // isasearch_index), starts its llama.cpp servers on first use, and follows new generations.
  class Search_Server(log: Logger) {
    private val process = Bash.process(
      File.bash_path(Path.explode("$ISABELLE_HOME/bin/isabelle")) + " isasearch_server -p 0",
      redirect = true, description = "isasearch_server")

    val url: String = {
      val output = new StringBuilder
      var result = ""
      while (result.isEmpty) {
        val line = proper_value(process.stdout.readLine()).getOrElse {
          process.terminate()
          error(cat_lines("isasearch_server stopped during startup:" ::
            split_lines(output.toString)))
        }
        output ++= line + "\n"
        result = Library.try_unprefix("IsaSearch API: ", line).map(Library.trim_string)
          .getOrElse("")
      }
      result.stripSuffix("/")
    }

    // Its further output goes to the log of PIDE AI.
    private val exit: Future[Int] = Future.thread("isasearch_server") {
      Iterator.continually(process.stdout.readLine()).takeWhile(_ != null)
        .foreach(line => log("isasearch_server: " + line))
      process.join()
    }

    def running: Boolean = !exit.is_finished

    def join(): Unit = exit.join_result

    def stop(): Unit = process.terminate()

    private val http = HttpClient.newHttpClient().nn

    // A first search may wait for a model download.
    // Copies of a statement come as one result.
    def search(
      query: String,
      kind: Corpus_Kind,
      limit: Int,
      expand: Boolean,
      filter: Search_Filter
    ): Obj = {
      def encode(s: String): String = URLEncoder.encode(s, "UTF-8").nn
      val parameters =
        List("query" -> query, "kind" -> kind.name, "limit" -> limit.toString,
          "refine_query" -> expand.toString, "collapse" -> "true") :::
        Search.filter_parameters(filter)
      val request = HttpRequest.newBuilder(URI.create(url + "/search?" +
          parameters.map { case (a, b) => encode(a) + "=" + encode(b) }.mkString("&"))).nn
        .timeout(Duration.ofHours(1)).nn.GET().nn.build().nn
      val response = http.send(request, HttpResponse.BodyHandlers.ofString()).nn
      val body =
        try { obj(JSON.parse(response.body().nn)) }
        catch { case ERROR(_) => error("isasearch_server answered HTTP " + response.statusCode()) }
      if (response.statusCode() == 200) body
      else error(proper_string(str(body, "error")).getOrElse("HTTP " + response.statusCode()))
    }
  }


  /** availability **/

  // Whether a hit can be used in a running session: its theory is in the heap of the base
  // session ("loaded"), its session is known there, so that the theory can be loaded from its
  // sources ("known"), or its session, e.g. an AFP entry, is missing ("unavailable").
  enum Availability(val name: String) {
    case Unavailable extends Availability("unavailable")
    case Known extends Availability("known")
    case Loaded extends Availability("loaded")
  }

  def availability(session: PIDE_AI_Session, record: Obj): Availability = {
    val background = session.resources.current_background
    if (background.base.loaded_theory(str(record, "theory"))) Availability.Loaded
    else if (background.sessions_structure.defined(str(record, "session"))) Availability.Known
    else Availability.Unavailable
  }

  // The AFP entry of a session: the directory below the AFP's thys.
  def afp_entry(info: Sessions.Info): Option[String] =
    if (!info.is_afp) None
    else {
      val elements = space_explode('/', File.standard_path(info.dir.expand))
      val i = elements.lastIndexOf("thys")
      if (i < 0 || i + 1 >= elements.length) None else Some(elements(i + 1))
    }

  // A filter narrowed to the hits of at least the given availability, as far as the index can
  // select them: by AFP entry for known sessions, by session for loaded theories. Results are
  // checked against the availability itself.
  def restrict(filter: Search_Filter, session: PIDE_AI_Session, least: Availability)
      : Search_Filter =
    if (least == Availability.Unavailable) filter
    else {
      val background = session.resources.current_background
      val structure = background.sessions_structure
      val sessions =
        if (least == Availability.Loaded)
          Some(background.base.loaded_theories.keys.map(structure.theory_qualifier).toSet)
        else None
      val names = sessions.getOrElse(structure.imports_topological_order.toSet)
      val entries = names.filter(structure.defined).flatMap(n => afp_entry(structure(n)))
      filter.copy(
        entries =
          if (!filter.source.afp) None
          else Some(filter.entries.fold(entries)(_.intersect(entries))),
        sessions = sessions.map(ss => filter.sessions.fold(ss)(_.intersect(ss))))
    }


  /** results for agents **/

  val statement_limit = 1500
  val description_limit = 800
  val names_limit = 20

  // The facts and constants a hit defines: compactly without the selections of a fact (e.g.
  // f.simps(2), which f.simps covers) and at most names_limit of them.
  def names(record: Obj, details: Boolean): (List[String], Int) = {
    val all = List("consts", "typs", "thms").flatMap(key => strings(record, key)).distinct
    if (details) (all, 0)
    else {
      val facts = all.map(name => name.replaceFirst("\\(\\d+\\)$", "").nn).distinct
      (facts.take(names_limit), (facts.length - names_limit) max 0)
    }
  }

  // A hit for agents: compactly what identifies, states and locates it; with details also its
  // description and online sources. Without a local file, the line and online source locate it.
  def result(
    record: Obj,
    session: Option[PIDE_AI_Session],
    details: Boolean,
    copies: List[Obj] = Nil
  ): JSON.Object.T = {
    def field(key: String): Option[String] = proper_string(str(record, key))
    val local = field("local_file")
    val online = details || local.isEmpty
    val (shown, more) = names(record, details)
    JSON_Object.flatten(
      Some("names" -> shown),
      if (more > 0) Some("more_names" -> more) else None,
      if (details) Some("command" -> str(record, "command")) else None,
      Some("theory" -> str(record, "theory")),
      field("entry").map("afp_entry" -> _),
      Search.qualifier(record).map("context" -> _),
      if (online) Some("line" -> num(record, "start_line", 0).toInt) else None,
      Some("statement" -> truncate(
        Library.trim_string(Text_Preparation.strip_proof(str(record, "src"))), statement_limit)),
      if (details) Some("description" -> truncate(str(record, "llm_description"),
        description_limit)) else None,
      Some("distance" -> math.rint(num(record, "distance", 0) * 10000) / 10000),
      session.map(s => "availability" -> availability(s, record).name),
      local.map("local_file" -> _),
      record.get("local_line").map("local_line" -> _),
      if (online) field("remote_url").orElse(field("theory_url")).map("online_url" -> _) else None,
      if (details) field("entry_url").map("entry_url" -> _) else None,
      if (copies.isEmpty) None
      else Some("copies" -> copies.map(copy => JSON_Object.flatten(
        names(copy, details = false)._1.headOption.map("name" -> _),
        Some("theory" -> str(copy, "theory")),
        proper_string(str(copy, "entry")).map("afp_entry" -> _),
        session.map(s => "availability" -> availability(s, copy).name)))))
  }

  // The copies of a statement as one hit: the most available copy, the first among equals.
  def collapsed(
    record: Obj,
    session: Option[PIDE_AI_Session],
    least: Availability,
    details: Boolean
  ): Option[JSON.Object.T] = {
    val copies = record.removed("copies") :: list(record.getOrElse("copies", Nil)).map(obj)
    val ranked = session match {
      case None => copies.map(_ -> Availability.Unavailable)
      case Some(s) => copies.map(c => c -> availability(s, c))
    }
    val (best, available) = ranked.maxBy(_._2.ordinal)
    if (available.ordinal < least.ordinal) None
    else Some(result(best, session, details, copies.filterNot(_ eq best)))
  }
}


class IsaSearch_Tool extends PIDE_AI_Tool("isasearch") with PIDE_AI_Tool.Read_Only {
  def description: String =
    "Semantic search of the theorems and definitions of the AFP and the Isabelle distribution " +
    "by what they state, in natural language. Ranked by the distance of the query to " +
    "LLM-written descriptions of the facts (smaller is closer); copies of a statement are one " +
    "hit. With a running session, every hit says whether that session has its theory loaded, " +
    "can load it, or lacks it, and the search can be restricted to what the session can use."

  val query_arg = JSON_Schema.Arg.required(
    "query", "What the theorem states or the definition defines, in plain mathematical " +
      "language; Isabelle notation works less well.", JSON_Schema.Format.string)
  val kind_arg = JSON_Schema.Arg.default(
    "kind", "Corpus to search.",
    JSON_Schema.Format.enumeration(Corpus_Kind.values.toList, _.name), Corpus_Kind.Theorems)
  val limit_arg = JSON_Schema.Arg.default(
    "limit", "Number of results.", JSON_Schema.Format.int(minimum = Some(1), maximum = Some(100)),
    10)
  val available_arg = JSON_Schema.Arg.default(
    "available", "Only hits that the running session can use: \"loaded\" (its theory is in the " +
      "session's heap), \"known\" (loaded, or loadable from the sources of a session it knows), " +
      "or \"any\".",
    JSON_Schema.Format.enumeration(IsaSearch_Tool.Availability.values.toList.reverse,
      a => if (a == IsaSearch_Tool.Availability.Unavailable) "any" else a.name),
    IsaSearch_Tool.Availability.Unavailable)
  val source_arg = JSON_Schema.Arg.default(
    "source", "Only hits of the Isabelle distribution or of the AFP.",
    JSON_Schema.Format.enumeration(Search_Source.values.toList, _.name), Search_Source.All)
  val entries_arg = JSON_Schema.Arg.optional(
    "entries", "Only hits of these AFP entries (directory names, e.g. \"Groebner_Bases\"), " +
      "besides the distribution unless source is \"afp\".",
    JSON_Schema.Format.list(JSON_Schema.Format.string))
  val mentions_arg = JSON_Schema.Arg.optional(
    "mentions", "Only hits whose statement mentions all of these: a name as a whole name " +
      "(\"countable\" does not match \"uncountable\"), a symbol (\"\\<Union>\" or \"⋃\") as " +
      "text. No spaces.",
    JSON_Schema.Format.list(JSON_Schema.Format.string))
  val details_arg = JSON_Schema.Arg.default(
    "details", "Also give the LLM-written description, every name, the command and the online " +
      "sources of each hit.", JSON_Schema.Format.bool, false)
  val expand_arg = JSON_Schema.Arg.default(
    "expand", "Let an LLM paraphrase the query first: seconds per query, and only if query " +
      "expansion is configured, which it is not by default.", JSON_Schema.Format.bool, false)

  def input_schema: JSON.Object.T = JSON_Schema.object_schema(
    List(PIDE_AI_Tool_Schema.running_session_arg, query_arg, kind_arg, limit_arg, available_arg,
      source_arg, entries_arg, mentions_arg, details_arg, expand_arg))


  /* search server */

  // Started on the first search, again if it has stopped, and stopped with PIDE AI.
  private val state = Synchronized[Option[IsaSearch_Tool.Search_Server]](None)

  private def search_server(server: PIDE_AI_Server): IsaSearch_Tool.Search_Server =
    state.change_result {
      case Some(running) if running.running => (running, Some(running))
      case _ =>
        val started = new IsaSearch_Tool.Search_Server(server.log)
        server.scope.fork("isasearch_server", new Task[Unit] {
          def run(): Unit = started.join()
          def stop(): Unit = started.stop()
        }, daemon = true)
        (started, Some(started))
    }


  /* tool calls */

  // The session of the call if it names one, or the unique running session if there is one.
  private def session(server: PIDE_AI_Server, args: JSON.Object.T): Option[PIDE_AI_Session] =
    PIDE_AI_Tool_Schema.running_session_arg.get(args) match {
      case Some(id) => server.sessions.running_sessions(Some(List(id))).headOption
      case None =>
        server.sessions.running_sessions(None) match {
          case List(session) => Some(session)
          case _ => None
        }
    }

  def handle(
    server: PIDE_AI_Server,
    args: JSON.Object.T,
    progress: Progress,
    context: PIDE_AI_Client_Context
  ): PIDE_AI_Tool_Result =
    PIDE_AI_Tool_Result.result {
      val running = session(server, args)
      val least = available_arg.get(args)
      val details = details_arg.get(args)
      val requested =
        try {
          Search_Filter(
            source = source_arg.get(args),
            entries = entries_arg.get(args).map(_.toSet),
            mentions = mentions_arg.get(args).getOrElse(Nil))
        }
        catch { case ERROR(msg) => error("Bad filter: " + msg) }
      val filter = running match {
        case Some(s) => IsaSearch_Tool.restrict(requested, s, least)
        case None if least == IsaSearch_Tool.Availability.Unavailable => requested
        case None => error("available needs a running session")
      }
      val response = search_server(server).search(
        query_arg.get(args), kind_arg.get(args), limit_arg.get(args), expand_arg.get(args), filter)
      JSON_Object.flatten(
        running.map(s => "session" -> s.id),
        proper_string(Data.str(response, "refined_query")).map("expanded_query" -> _),
        Some("results" ->
          Data.list(response.getOrElse("results", Nil))
            .flatMap(r => IsaSearch_Tool.collapsed(Data.obj(r), running, least, details))))
    }
}


class IsaSearch_Tools extends PIDE_AI_Tools(new IsaSearch_Tool)
