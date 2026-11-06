/*  Title:      IsaSearch/pide_ai/src/isasearch_tool.scala

Semantic search of the AFP and the Isabelle distribution as a tool of PIDE AI.
*/

package isabelle.isasearch.pide_ai


import isabelle._
import isabelle.pide.ai.{JSON_Object, JSON_Schema, PIDE_AI_Client_Context, PIDE_AI_Server,
  PIDE_AI_Session, PIDE_AI_Tool, PIDE_AI_Tool_Result, PIDE_AI_Tool_Schema, PIDE_AI_Tools, Task}
import isabelle.isasearch.{Corpus_Kind, Data, Text_Preparation}

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
    def search(query: String, kind: Corpus_Kind, limit: Int, expand: Boolean): Obj = {
      def encode(s: String): String = URLEncoder.encode(s, "UTF-8").nn
      val request = HttpRequest.newBuilder(URI.create(url + "/search?query=" + encode(query) +
          "&kind=" + kind.name + "&limit=" + limit + "&refine_query=" + expand)).nn
        .timeout(Duration.ofHours(1)).nn.GET().nn.build().nn
      val response = http.send(request, HttpResponse.BodyHandlers.ofString()).nn
      val body =
        try { obj(JSON.parse(response.body().nn)) }
        catch { case ERROR(_) => error("isasearch_server answered HTTP " + response.statusCode()) }
      if (response.statusCode() == 200) body
      else error(proper_string(str(body, "error")).getOrElse("HTTP " + response.statusCode()))
    }
  }


  /** results for agents **/

  val statement_limit = 1500
  val description_limit = 800

  // Whether a hit can be used in a running session: its theory is in the heap of the base
  // session ("loaded"), its session is known there, so that the theory can be loaded from its
  // sources ("known"), or its session, e.g. an AFP entry, is missing ("unavailable").
  def availability(session: PIDE_AI_Session, record: Obj): String = {
    val background = session.resources.current_background
    if (background.base.loaded_theory(str(record, "theory"))) "loaded"
    else if (background.sessions_structure.defined(str(record, "session"))) "known"
    else "unavailable"
  }

  // The local file and the line of the source there, where this machine has the file, and the
  // online sources: the file in the AFP repository or the theory in the Isabelle library, and
  // the page of the AFP entry.
  def result(record: Obj, session: Option[PIDE_AI_Session]): JSON.Object.T = {
    val names = List("thms", "consts", "typs").flatMap(key => strings(record, key)).distinct
    def field(key: String): Option[String] = proper_string(str(record, key))
    JSON_Object.flatten(
      Some("names" -> names),
      Some("command" -> str(record, "command")),
      Some("theory" -> str(record, "theory")),
      field("entry").map("afp_entry" -> _),
      Some("line" -> num(record, "start_line", 0).toInt),
      Some("statement" -> truncate(
        Library.trim_string(Text_Preparation.strip_proof(str(record, "src"))), statement_limit)),
      Some("description" -> truncate(str(record, "llm_description"), description_limit)),
      Some("distance" -> math.rint(num(record, "distance", 0) * 10000) / 10000),
      session.map(s => "availability" -> availability(s, record)),
      field("local_file").map("local_file" -> _),
      record.get("local_line").map("local_line" -> _),
      field("remote_url").orElse(field("theory_url")).map("online_url" -> _),
      field("entry_url").map("entry_url" -> _))
  }
}


class IsaSearch_Tool extends PIDE_AI_Tool("isasearch") with PIDE_AI_Tool.Read_Only {
  def description: String =
    "Semantic search of the theorems and definitions of the AFP and the Isabelle distribution " +
    "by what they state, in natural language. Ranked by the distance of the query to " +
    "LLM-written descriptions of the facts (smaller is closer). With a running session, " +
    "every hit says whether that session has its theory loaded, can load it, or lacks it."

  val query_arg = JSON_Schema.Arg.required(
    "query", "What the theorem states or the definition defines, in natural language; " +
      "Isabelle notation is fine.", JSON_Schema.Format.string)
  val kind_arg = JSON_Schema.Arg.default(
    "kind", "Corpus to search.",
    JSON_Schema.Format.enumeration(Corpus_Kind.values.toList, _.name), Corpus_Kind.Theorems)
  val limit_arg = JSON_Schema.Arg.default(
    "limit", "Number of results.", JSON_Schema.Format.int(minimum = Some(1), maximum = Some(100)),
    10)
  val expand_arg = JSON_Schema.Arg.default(
    "expand", "Let the configured LLM expand the query first; seconds per query, and only if " +
      "query expansion is configured.", JSON_Schema.Format.bool, false)

  def input_schema: JSON.Object.T = JSON_Schema.object_schema(
    List(PIDE_AI_Tool_Schema.running_session_arg, query_arg, kind_arg, limit_arg, expand_arg))


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
      val response = search_server(server).search(
        query_arg.get(args), kind_arg.get(args), limit_arg.get(args), expand_arg.get(args))
      JSON_Object.flatten(
        running.map(s => "session" -> s.id),
        proper_string(Data.str(response, "refined_query")).map("expanded_query" -> _),
        Some("results" ->
          Data.list(response.getOrElse("results", Nil))
            .map(r => IsaSearch_Tool.result(Data.obj(r), running))))
    }
}


class IsaSearch_Tools extends PIDE_AI_Tools(new IsaSearch_Tool)
