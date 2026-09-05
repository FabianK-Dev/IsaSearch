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
        progress_stdout = line => Output.writeln(line, stdout = true),
        progress_stderr = Output.writeln(_)
      )
      if (!result.ok) sys.exit(result.rc)
    }
  )
}


class Tools extends Isabelle_Scala_Tools(Tool_Entries.names.map(Tool_Entries.tool): _*)

object Main {
  def main(argv: Array[String]): Unit = Command_Line.tool {
    import Data._
    if (argv.isEmpty) error("Missing IsaSearch tool name")
    val tool = Tool_Command.parse(argv.head)
    var config_path: Option[Path] = None
    var index = Options.init().string("isasearch_index")
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
  -i NAME   built index name (default local)
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
  -a        report all duplicate candidates
  -s LIST   benchmark strategies: baseline,R,UR,M,MR,MUR or all
  -v        verbose progress

Import: -f EXPORT_DIR. Index: SESSION ... (or isabelle_sessions in config).
Search: QUERY. Index_build: -D component output directory.
Benchmark never builds indexes; supply the required prebuilt variants.
"""
    val getopts = Getopts(
      usage,
      "c:" -> (s => config_path = Some(Path.explode(s))),
      "i:" -> (s => index = safe_name(s)),
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
    val config = config_path.map(p => Config(read(p), p.absolute.dir)).getOrElse(Config(Map.empty))
    val progress = new Console_Progress(verbose = verbose)
    tool match {
      case Tool_Command.Import =>
        Index.import_index(input.getOrElse(error("Use -f EXPORT_DIR")), index, progress)
      case Tool_Command.Index => Corpus_Build.run(config, index, args, no_build, progress)
      case Tool_Command.Package_Index => progress.echo(Index.package_index(index, out).implode)
      case Tool_Command.Test => Tests.run(args)
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
