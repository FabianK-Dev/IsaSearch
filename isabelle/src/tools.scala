/*  Title:      IsaSearch/isabelle/src/tools.scala

Command-line entry points of the isasearch_* tools (lib/Tools), which run in a JVM of their own
with Solr's classpath (lib/scripts/isasearch).
*/

package isabelle.isasearch


import isabelle._


/* progress */

// Console progress that also appends every message to a log file, without the transient
// status lines of running theories.
class Logged_Progress(log: Path, verbose: Boolean) extends Console_Progress(verbose = verbose) {
  Isabelle_System.make_directory(log.dir)

  override def status_output(msgs: Progress.Output): Unit = synchronized {
    super.status_output(msgs)
    val text = output_text(msgs.filterNot(_.status), terminate = true)
    if (text.nonEmpty) File.append(log, text)
  }
}

object Main {
  private val log_date = Date.Format("uuuuMMdd-HHmmss")

  def main(argv: Array[String]): Unit = Command_Line.tool {
    import Data._
    if (argv.isEmpty) error("Missing IsaSearch tool name")
    val tool = Tool_Command.parse(argv.head)
    var options = Options.init()
    var config_paths = List.empty[Path]
    var index_names = List.empty[String]
    var metadata_index = ""
    var out = home + Path.basic("reports")
    var input: Option[Path] = None
    var port: Option[Int] = None
    var refine = false
    var no_build = false
    var cross = false
    var judge = true
    var all = false
    var verbose = false
    var newest = 10
    var selected_kinds: Option[List[Corpus_Kind]] = None
    var export_format = Export_Format.Generation
    var entries = List.empty[String]
    var strategies = List(Benchmark_Strategy.Baseline)
    val usage = """
Usage: isabelle isasearch_""" + tool + """ [OPTIONS] [ARGS ...]

  -c FILE   JSON configuration (paths relative to this file); searching tools
            default to option isasearch_config
  -i NAME   index name (default option isasearch_index: """ +
      options.string("isasearch_index") + """); index: repeat
            -c FILE -i NAME to build several indexes from one session build
  -m NAME   benchmark index built with metadata
  -D DIR    output directory (reports, component or export parent)
  -f PATH   exported index directory (import) or benchmark CSV
  -F FORMAT export format: generation (default) or interchange
  -o OPTION override Isabelle system OPTION (via NAME=VAL or NAME)
  -p PORT   API port (default option isasearch_port: 5001; loopback only)
  -r        expand the query (search only; default off)
  -n        use existing Isabelle session build databases (index)
  -k KINDS  theorems, definitions, or all (comma separated for duplicates)
  -e ENTRY  analyse AFP entry (repeatable; duplicates)
  -N COUNT  analyse newest entries (default 10)
  -x        cross-kind duplicate analysis
  -J        disable LLM duplicate judge
  -a        retain unclassified duplicate candidates in JSON
  -s LIST   benchmark strategies: baseline,R,UR,M,MR,MUR or all
  -v        verbose progress

Import: -f DIR, an exported generation (installed as it is, moving DIR when it
  is on the same file system) or interchange data (indexed anew).
Index: SESSION ... (or isabelle_sessions in config).
Search: QUERY. Index_build: -D component output directory.
Export: -D DIR writes the current generation to DIR/isasearch-NAME, ready to
  search, or as interchange data for other Lucene versions and tools.
Server: follows the index to every newly published generation.
Prune: removes the generations other than the current one.
Benchmark never builds indexes; supply the required prebuilt variants.
Compare: PREVIOUS CURRENT (result files or strategy directories of benchmark runs).
"""
    val getopts = Getopts(
      usage,
      "c:" -> (s => config_paths = config_paths :+ Path.explode(s)),
      "i:" -> (s => index_names = index_names :+ safe_name(s)),
      "m:" -> (s => metadata_index = safe_name(s)),
      "D:" -> (s => out = Path.explode(s)),
      "f:" -> (s => input = Some(Path.explode(s))),
      "F:" -> (s => export_format = Export_Format.parse(s)),
      "o:" -> (s => options = options + s),
      "p:" -> (s => port = Some(Value.Int.parse(s))),
      "r" -> (_ => refine = true),
      "n" -> (_ => no_build = true),
      "k:" -> (s =>
        selected_kinds =
          Some(if (s == "all") Index.kinds else s.split(',').toList.map(Corpus_Kind.parse))
      ),
      "e:" -> (s => entries = entries :+ s),
      "N:" -> (s => newest = Value.Int.parse(s)),
      "x" -> (_ => cross = true),
      "J" -> (_ => judge = false),
      "a" -> (_ => all = true),
      "s:" -> (s =>
        strategies =
          if (s == "all") Benchmark.strategies
          else s.split(',').toList.map(Benchmark_Strategy.parse)
      ),
      "v" -> (_ => verbose = true)
    )
    val args = getopts(argv.tail.toList)
    // Only isasearch_index pairs repeated -c and -i options; elsewhere the last one counts.
    val config = config_paths.lastOption.map(Config.load).getOrElse(
      if (tool.searches) Config.default(options) else Config(Map.empty))
    val index = index_names.lastOption.getOrElse(options.string("isasearch_index"))
    // Index builds run for days: their progress is also kept in a log file.
    val names = if (index_names.isEmpty) List(index) else index_names
    val log = home + Path.explode("logs") +
      Path.basic(("index" :: log_date(Date.now()) :: names).mkString("-") + ".log")
    val progress =
      if (tool == Tool_Command.Index) new Logged_Progress(log, verbose = verbose)
      else new Console_Progress(verbose = verbose)
    tool match {
      case Tool_Command.Import =>
        Index.import_index(input.getOrElse(error("Use -f EXPORT_DIR")), index, progress)
      case Tool_Command.Index =>
        val builds =
          if (index_names.isEmpty && config_paths.size <= 1) List(config -> index)
          else if (config_paths.size == index_names.size) config_paths.map(Config.load).zip(index_names)
          else error("Pair each configuration -c FILE with an index name -i NAME")
        for ((build, _) <- builds; role <- Llama_Server.roles(build))
          error(role.key + " serves searches; builds use " + role.endpoint)
        progress.echo("Log: " + log.expand.implode)
        Corpus_Build.run(builds, args, no_build, progress)
      case Tool_Command.Package_Index => progress.echo(Index.package_index(index, out).implode)
      case Tool_Command.Export =>
        progress.echo(Index.export_index(index, out, export_format, progress).implode)
      case Tool_Command.Prune => Index.prune(index).foreach(p => progress.echo("Removed " + p))
      case Tool_Command.Test => Tests.run(args)
      case Tool_Command.Integration_Test => Integration_Tests.run(progress)
      case Tool_Command.Compare =>
        args match {
          case List(previous, current) => Benchmark_Comparison.run(previous, current, progress)
          case _ => error("Specify the previous and the current benchmark result")
        }
      case Tool_Command.Benchmark =>
        val csv = input.getOrElse(Benchmark.default_csv)
        using(new Llama_Server.Servers(config)) { servers =>
          Benchmark
            .run(servers, index, metadata_index, csv, strategies, out, progress)
            .foreach(p => progress.echo(p.implode))
        }
      case Tool_Command.Search =>
        using(new Llama_Server.Servers(config)) { servers =>
          using(new Index.Pinned(Index.current(index))) { source =>
            val kind = selected_kinds.getOrElse(List(Corpus_Kind.Theorems)) match {
              case List(single) => single
              case _ => error("Search requires exactly one corpus kind")
            }
            val mode = if (refine) Query_Mode.Combined else Query_Mode.Original
            val engine = new Search.Engine(source, servers)
            progress.echo(JSON.Format(engine.search(args.mkString(" "), kind, mode)))
          }
        }
      case Tool_Command.Serve =>
        using(new Llama_Server.Servers(config)) { servers =>
          using(new Index.Live(index)) { source =>
            val server = Search.server(new Search.Engine(source, servers),
              port.getOrElse(options.int("isasearch_port")),
              editors = Isabelle_Editor.list(options.string("isasearch_editors")))
            server.start()
            progress.echo("IsaSearch API: " + server.url)
            try { new java.util.concurrent.CountDownLatch(1).await() }
            finally { server.stop() }
          }
        }
      case Tool_Command.Duplicates =>
        val kinds = selected_kinds.getOrElse(List(Corpus_Kind.Definitions))
        if (newest < 1 || kinds.isEmpty || kinds.exists(k => !Index.kinds.contains(k)))
          error("Invalid duplicate selection")
        using(new Llama_Server.Servers(config)) { servers =>
          using(new Index.Pinned(Index.current(index))) { source =>
            val engine = new Search.Engine(source, servers)
            progress.echo(Duplicates.run(engine, source.snapshot, entries, newest, kinds, cross,
              judge, all, out).implode)
          }
        }
    }
  }
}
