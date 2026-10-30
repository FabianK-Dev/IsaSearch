/*  Title:      IsaSearch/isabelle/src/tools.scala

Isabelle tool registration and command-line entry points.
*/

package isabelle.isasearch


import isabelle._


object Tool_Entries {
  val names = Tool_Command.values.toList

  def tool(command: Tool_Command): Isabelle_Tool = Isabelle_Tool(
    "isasearch_" + command.name,
    "IsaSearch " + command.name.replace('_', ' '),
    Scala_Project.here,
    args => {
      val script = "bash " + File.bash_path(Data.component + Path.explode("lib/Tools/isasearch")) +
        " " + Bash.strings(command.name :: args)
      val result = Isabelle_System.bash(
        script,
        progress_stdout = line => Output.writeln(line, stdout = true, include_empty = true),
        progress_stderr = line => Output.writeln(line, include_empty = true)
      )
      if (!result.ok) sys.exit(result.rc)
    }
  )
}


class Tools extends Isabelle_Scala_Tools(Tool_Entries.names.map(Tool_Entries.tool): _*)


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
    var config_paths = List.empty[Path]
    var index_names = List.empty[String]
    var metadata_index = ""
    var out = home + Path.basic("reports")
    var input: Option[Path] = None
    var port = Options.init().int("isasearch_port")
    var refine = false
    var no_build = false
    var cross = false
    var judge = true
    var all = false
    var verbose = false
    var newest = 10
    var selected_kinds: Option[List[Corpus_Kind]] = None
    var entries = List.empty[String]
    var strategies = List(Benchmark_Strategy.Baseline)
    val usage = """
Usage: isabelle isasearch_""" + tool + """ [OPTIONS] [ARGS ...]

  -c FILE   JSON configuration (paths relative to this file)
  -i NAME   built index name (default local); index: repeat -c FILE -i NAME
            to build several indexes from one session build
  -m NAME   benchmark index built with metadata
  -D DIR    output directory (reports or component parent)
  -f PATH   interchange directory (import) or benchmark CSV
  -p PORT   API port (default 5001; loopback only)
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

Import: -f EXPORT_DIR. Index: SESSION ... (or isabelle_sessions in config).
Seed: ARTIFACT ... (description artifacts of the Python implementation).
Search: QUERY. Index_build: -D component output directory.
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
      "p:" -> (s => port = Value.Int.parse(s)),
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
    def load(p: Path): Config = Config(read(p), p.absolute.dir)
    val config = config_paths.lastOption.map(load).getOrElse(Config(Map.empty))
    val index = index_names.lastOption.getOrElse(Options.init().string("isasearch_index"))
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
          else if (config_paths.size == index_names.size) config_paths.map(load).zip(index_names)
          else error("Pair each configuration -c FILE with an index name -i NAME")
        progress.echo("Log: " + log.implode)
        Corpus_Build.run(builds, args, no_build, progress)
      case Tool_Command.Seed => Seed.run(config, args.map(Path.explode), progress)
      case Tool_Command.Package_Index => progress.echo(Index.package_index(index, out).implode)
      case Tool_Command.Test => Tests.run(args)
      case Tool_Command.Integration_Test => Integration_Tests.run(progress)
      case Tool_Command.Compare =>
        args match {
          case List(previous, current) => Benchmark_Comparison.run(previous, current, progress)
          case _ => error("Specify the previous and the current benchmark result")
        }
      case Tool_Command.Benchmark =>
        val csv = input.getOrElse(Benchmark.default_csv)
        Benchmark
          .run(config, index, metadata_index, csv, strategies, out, progress)
          .foreach(p => progress.echo(p.implode))
      case Tool_Command.Search | Tool_Command.Serve | Tool_Command.Duplicates =>
        using(new Index.Snapshot(Index.current(index))) { snapshot =>
          val engine = new Search.Engine(snapshot, config)
          tool match {
            case Tool_Command.Search =>
              progress.echo(
                JSON.Format(
                  engine.search(
                    args.mkString(" "),
                    selected_kinds.getOrElse(List(Corpus_Kind.Theorems)) match {
                      case List(single) => single
                      case _ => error("Search requires exactly one corpus kind")
                    },
                    if (refine) Query_Mode.Combined else Query_Mode.Original
                  )
                )
              )
            case Tool_Command.Serve =>
              val server = Search.server(engine, port)
              server.start()
              progress.echo("IsaSearch API: " + server.url)
              try { new java.util.concurrent.CountDownLatch(1).await() }
              finally { server.stop() }
            case _ =>
              val kinds = selected_kinds.getOrElse(List(Corpus_Kind.Definitions))
              if (newest < 1 || kinds.isEmpty || kinds.exists(k => !Index.kinds.contains(k)))
                error("Invalid duplicate selection")
              progress.echo(
                Duplicates.run(engine, entries, newest, kinds, cross, judge, all, out).implode
              )
          }
        }
    }
  }
}
