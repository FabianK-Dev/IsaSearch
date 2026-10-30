/*  Title:      IsaSearch/isabelle/src/corpus.scala

AFP discovery, corpus preparation, and resumable index construction.
*/

package isabelle.isasearch


import isabelle._

import isabelle.find_facts.{Find_Facts, Solr}

import java.nio.file.Files
import java.util.concurrent.{Callable, Executors}


object Corpus_Build {
  import Data._


  /** registered AFP **/

  def afp_root: Path = {
    if (Isabelle_System.getenv("AFP_BASE").isEmpty)
      error(
        "No registered AFP component. Register the installed AFP with isabelle components -u /path/to/afp"
      )
    val root = AFP.BASE.expand
    if (!(AFP.main_dir(root) + Path.basic("ROOTS")).is_file ||
        !(root + Path.basic("metadata")).is_dir)
      error("Registered AFP component is incomplete: " + root.implode)
    root
  }

  def sessions(
    config: Config,
    options: Options,
    afp: Path,
    supplied: List[String]
  ): List[String] = {
    val structure = Sessions.load_structure(options, dirs = AFP.main_dirs(Some(afp)))
    val requested = if (supplied.nonEmpty) supplied else strings(config.values, "isabelle_sessions")
    if (requested.isEmpty) error("Select sessions as arguments or set isabelle_sessions")

    def hol(name: String): Boolean = name == "HOL" || structure(name).parent.exists(hol)
    def documentation(name: String): Boolean = structure(name).groups.contains("doc")

    val expanded = requested.flatMap {
      case "all" =>
        structure.imports_topological_order
          .filter(n => structure(n).is_afp || hol(n) && !documentation(n))
      case "all-AFP" => structure.imports_topological_order.filter(n => structure(n).is_afp)
      case name =>
        if (!structure.defined(name)) error("Unknown Isabelle session: " + name) else List(name)
    }
    for (name <- session_options(config).keys if !structure.defined(name))
      error("Unknown Isabelle session in isabelle_session_options: " + name)
    val excluded = strings(config.values, "isabelle_excluded_sessions").toSet
    expanded.distinct.filterNot(excluded)
  }

  // Option updates for particular sessions, in the syntax of isabelle build -o. They apply
  // after the session's ROOT options, e.g. timeout_scale=1 for a session whose SMT
  // certificates are keyed by the unscaled solver timeout.
  def session_options(config: Config): Map[String, List[String]] =
    object_at(config.values, "isabelle_session_options").map { case (session, specs) =>
      session -> list(specs).map {
        case spec: String => spec
        case _ =>
          error("Expected option strings for session " + session + " in isabelle_session_options")
      }
    }


  /** source provenance **/

  // Working-directory revision, marked "+" when modified; unlike AFP.hg_id, which is the tip.
  def revision(root: Path): Option[String] =
    Mercurial.archive_id(root) orElse Mercurial.id_repository(root, rev = "") orElse
      Mercurial.Hg_Sync.id_directory(root)

  def provenance(afp: Path, progress: Progress): Obj = {
    val isabelle_id =
      try { Some(Isabelle_System.isabelle_id()) } catch { case ERROR(_) => None }
    val afp_id = revision(afp)
    if (afp_id.isEmpty)
      progress.echo_warning("Unknown AFP revision: use a Mercurial clone or hg archive of " +
        afp.implode)
    if (afp_id.exists(_.endsWith("+")))
      progress.echo_warning("AFP working directory has local changes: " + afp.implode)
    Map(
      "isabelle" -> Map(
        "identifier" -> Isabelle_System.isabelle_identifier().orNull,
        "id" -> isabelle_id.orNull
      ),
      "afp" -> Map(
        "version" -> Isabelle_System.getenv("AFP_VERSION"),
        "id" -> afp_id.orNull
      )
    )
  }


  /** source metadata **/

  def metadata(root: Path, entry: String): Obj = {
    if (entry.isEmpty) return Map.empty
    // Entry names are AFP directory names, e.g. CoreC++: Path.basic accepts exactly one element.
    val file = root + Path.explode("metadata/entries") + Path.basic(entry).ext("toml")
    if (!file.is_file) return Map.empty
    val table = TOML.parse(File.read(file))
    Map(
      "title" -> table.string.get("title").map(_.rep).getOrElse(""),
      "abstract" -> table.string.get("abstract").map(_.rep).getOrElse(""),
      "date" -> table.local_date.get("date").map(_.rep.toString).getOrElse("")
    )
  }

  private def afp_relative(file: String, afp: Path): Option[String] = {
    // FindFacts serializes Path.squash: environment references lose their '$' marker.
    // Session exports can contain canonical paths (e.g. /private/var instead of /var).
    val roots = List(Path.explode("$AFP"), AFP.main_dir(), AFP.main_dir(afp),
      AFP.main_dir(afp).canonical)
    roots.map(_.squash.implode + "/").find(file.startsWith).map(file.stripPrefix)
  }

  // The FindFacts fields of a block that a corpus document retains.
  def source(block: Find_Facts.Block): Obj =
    Map(
      "id" -> block.id,
      "src" -> block.src,
      "entity_kname" -> block.entity_kname.orNull,
      "chapter" -> block.chapter,
      "session" -> block.session,
      "theory" -> block.theory,
      "file" -> block.file,
      "url_path" -> block.url_path.implode,
      "command" -> block.command,
      "start_line" -> block.start_line,
      "consts" -> block.consts,
      "typs" -> block.typs,
      "thms" -> block.thms
    )

  def source_record(
    block: Obj,
    relative: Option[String],
    meta: Obj,
    config: Config
  ): Obj = {
    val e = relative.map(_.takeWhile(_ != '/')).getOrElse("")
    val library = config.string("isabelle_remote_theory_url", "https://isabelle.in.tum.de/library")
    val url_path = str(block, "url_path")
    val start_line = num(block, "start_line", 0).toInt
    block ++ Map(
      "entry" -> e,
      "entry_date" -> str(meta, "date"),
      "metadata" -> meta,
      // The Isabelle library hosts only distribution theories; AFP sources use remote_url.
      "theory_url" -> (if (e.nonEmpty) "" else library.stripSuffix("/") + "/" + url_path),
      "entry_url" -> (if (e.isEmpty) ""
                      else
                        config
                          .string("afp_remote_entry_url", "https://isa-afp.org/entries")
                          .stripSuffix("/") + "/" + e + ".html"),
      "remote_url" -> (if (e.isEmpty) ""
                       else
                         config
                           .string(
                             "afp_remote_thys_folder_url",
                             "https://foss.heptapod.net/isa-afp/afp-" + Isabelle_System
                               .getenv_strict("AFP_VERSION") + "/-/tree/branch/default/thys"
                           )
                           .stripSuffix("/") + "/" + relative.get + "#L" + start_line)
    )
  }


  /** build configuration **/

  // Builds the indexes in order. Indexes that request the same session build share it, and
  // with it the FindFacts index, e.g. the plain and the metadata variant of one corpus.
  def run(
    builds: List[(Config, String)],
    supplied: List[String],
    no_build: Boolean,
    progress: Progress
  ): List[Path] = {
    val names = builds.map(_._2)
    if (names.distinct.size < names.size) error("Duplicate index names: " + commas(names))
    val afp = afp_root
    var shared = Map.empty[Build_Request, (String, Built)]
    for ((config, name) <- builds) yield {
      val request = Build_Request(
        sessions(config, Options.init(), afp, supplied),
        config.number("isabelle_timeout_scale", 1),
        session_options(config),
        config.positive("isabelle_build_jobs", 1),
        no_build
      )
      def build(): Built =
        shared.get(request) match {
          case Some((previous, built)) =>
            progress.echo("Using the session builds of index " + previous)
            built
          case None =>
            val built = build_sessions(request, afp, progress)
            shared += request -> (name, built)
            built
        }
      run_index(config, name, request, build, afp, progress)
    }
  }

  private def run_index(
    config: Config,
    name: String,
    request: Build_Request,
    build: () => Built,
    afp: Path,
    progress: Progress
  ): Path = {
    val selected = request.sessions
    if (selected.isEmpty) error("No sessions remain after exclusions")
    progress.echo("Index " + name + " from AFP " + afp.implode + "; sessions: " +
      selected.mkString(", "))
    val excluded = strings(config.values, "isabelle_excluded_sessions")
    if (excluded.nonEmpty) progress.echo("Excluded sessions: " + excluded.mkString(", "))
    for ((session, specs) <- session_options(config).toList.sortBy(_._1))
      progress.echo("Session options for " + session + ": " + specs.mkString(", "))
    val prompt_base =
      if (config.string("prompts_folder").isEmpty) component + Path.explode("prompts/qwen3-gemma")
      else config.path("prompts_folder", "")
    val prompt_dir =
      if (config.boolean("add_metadata")) Path.explode(prompt_base.implode + "-with-metadata")
      else prompt_base
    val prompts: Obj = File
      .read_dir(prompt_dir)
      .filter(_.endsWith(".txt"))
      .map { f =>
        f.stripSuffix(".txt") -> File.read(prompt_dir + Path.basic(f))
      }
      .toMap
    val inference = new Inference.Client(config)
    if (!inference.configured(Model_Role.Document))
      error("Configure a document LLM to build a corpus")
    val recipe: Obj = Map(
      "model" -> inference.embedding_model,
      "backend" -> config.string("embedding_backend", "openai"),
      "max_characters" -> config.positive("openai_embedding_max_characters", 8000),
      "add_metadata" -> config.boolean("add_metadata"),
      "document_model" -> inference.model(Model_Role.Document),
      "prompts" -> prompts
    )
    val workspace = Isabelle_System.make_directory(home + Path.explode("build/" + safe_name(name)))
    using(
      java.nio.channels.FileChannel.open(
        (workspace + Path.basic("build.lock")).java_path,
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.WRITE
      )
    ) { channel =>
      val lock = proper_value(channel.tryLock())
        .getOrElse(error("Another corpus build is running for " + name))
      try {
        build_locked(config, name, request, build, progress, afp, recipe, inference, workspace)
      }
      finally { lock.release() }
    }
  }


  /** resumable inference **/

  // Descriptions and vectors are kept in the stores of Inference.Client, keyed by their
  // inputs; records are rebuilt from the current blocks, so positions and links stay current.
  private class Preparation(
    config: Config,
    afp: Path,
    recipe: Obj,
    inference: Inference.Client
  ) {
    val space = Embedding_Space(
      recipe,
      Distance_Metric.parse(config.string("distance_metric", Distance_Metric.Cosine.name))
    )
    private val metadata_cache = scala.collection.concurrent.TrieMap.empty[String, Obj]
    private val prompts = object_at(recipe, "prompts")

    def prompt(block: Obj, kind: Corpus_Kind, meta: Obj): String = {
      val prompt_template = prompts
        .get(kind.describe_key)
        .map(_.asInstanceOf[String])
        .getOrElse(error("Missing prompt: " + kind.describe_key))
      val with_metadata = config.boolean("add_metadata")
      val title = if (with_metadata) Text_Preparation.metadata(str(meta, "title")) else ""
      val abstract_text =
        if (with_metadata) Text_Preparation.metadata(str(meta, "abstract")) else ""
      val metadata_limit = config.integer("metadata_max_length", 300)
      val abstract_excerpt =
        if (title.length + abstract_text.length > metadata_limit)
          truncate(abstract_text, math.max(0, metadata_limit - title.length - 3)) + "..."
        else abstract_text
      template(
        prompt_template,
        Map(
          "theorem_content" -> Library.trim_string(truncate(
            Text_Preparation.strip_proof(str(block, "src")),
            config.positive("theorem_max_length", 3000)
          )),
          "title" -> (if (title.isEmpty) "-- no title --" else title),
          "abstract" -> (if (abstract_excerpt.isEmpty) "-- no abstract --"
                         else abstract_excerpt)
        )
      )
    }

    // The document, and whether its description came from the store.
    def describe(block: Obj, kind: Corpus_Kind): (Obj, Boolean) = {
      val src = str(block, "src")
      val relative = afp_relative(str(block, "file"), afp)
      val entry_name = relative.map(_.takeWhile(_ != '/')).getOrElse("")
      val meta = metadata_cache.getOrElseUpdate(entry_name, metadata(afp, entry_name))
      val text = prompt(block, kind, meta)
      val completion = inference.generate(text, role = Model_Role.Document, cached = true)
      val checksum = new java.util.zip.Adler32()
      checksum.update(UTF8.bytes(src))
      val description = marked(completion.text)
      val document = source_record(block, relative, meta, config) ++ Map(
        "kind" -> kind.name,
        "checksum" -> checksum.getValue,
        "llm_description" -> description,
        "embedding_input" -> template(
          str(prompts, Prompt.Embed),
          Map("doc_src" -> (description + "\n\n" + Library.trim_string(src)))
        ),
        "description_artifact" -> Map(
          "llm_description" -> completion.text,
          "prompt" -> text,
          "zlib.adler32_checksum" -> checksum.getValue
        )
      )
      (document, completion.cached)
    }

    def vectors(documents: Seq[Obj]): List[Array[Float]] =
      inference.embed_stored(documents.map(str(_, "embedding_input")).toList, space)
  }


  /** pruning safeguards **/

  private def identity(document: Obj): String = {
    val entity = str(document, "entity_kname")
    if (entity.isEmpty) str(document, "id")
    else str(document, "file") + "|" + entity
  }

  private def guard_pruning(
    name: String,
    kind: Corpus_Kind,
    present: Set[String],
    config: Config
  ): Unit = {
    val pointer = Index.location(name) + Path.basic("current.json")
    if (pointer.is_file) using(new Index.Snapshot(Index.current(name))) { previous =>
      previous.corpora.get(kind).foreach { corpus =>
        val old = corpus.all.map(r => identity(r._2)).toSet
        if (old.nonEmpty && old.diff(present).size > old.size / 2 &&
            !config.boolean("allow_large_prune"))
          error(
            "Refusing to prune more than half of " + kind + "; inspect selection and set allow_large_prune explicitly"
          )
      }
    }
  }


  /** corpus output **/

  private def write_corpus(
    blocks: Iterator[Obj],
    kind: Corpus_Kind,
    preparation: Preparation,
    executor: java.util.concurrent.ExecutorService,
    config: Config,
    name: String,
    recipe: Obj,
    output: Path,
    progress: Progress
  ): Option[Obj] = {
    val directory = Isabelle_System.make_directory(output + Path.basic(kind.name))
    var dimension = 0
    val seen = scala.collection.mutable.HashSet.empty[String]
    val identities = scala.collection.mutable.HashSet.empty[String]
    var reused = 0
    using(Files.newBufferedWriter((directory + Path.basic(Index_Format.documents)).java_path)) { docs =>
      using(Files.newOutputStream((directory + Path.basic(Index_Format.vectors)).java_path)) { vectors =>
        blocks.grouped(config.positive("openai_embedding_batch_size", 32)).foreach { batch =>
          val tasks = batch.map { block =>
            executor.submit(new Callable[(Obj, Boolean)] {
              def call(): (Obj, Boolean) = preparation.describe(block, kind)
            }).nn
          }
          val (described, stored) = tasks.map { task =>
            try { task.get().nn }
            catch {
              case exn: java.util.concurrent.ExecutionException =>
                throw proper_value(exn.getCause).getOrElse(exn)
            }
          }.unzip
          reused += stored.count(b => b)
          for ((doc, vector) <- described.zip(preparation.vectors(described))) {
            if (!seen.add(str(doc, "id"))) error("Duplicate source ID")
            identities += identity(doc)
            if (dimension == 0) dimension = vector.length
            validate(vector, dimension, preparation.space.metric)
            docs.write(JSON.Format(doc))
            docs.newLine()
            vectors.write(bytes(vector))
          }
          progress.echo("Prepared " + seen.size + " " + kind + " (" + reused +
            " stored descriptions reused)")
        }
      }
    }
    guard_pruning(name, kind, identities.toSet, config)
    if (seen.isEmpty) None
    else
      Some(
        Map(
          "kind" -> kind.name,
          "count" -> seen.size,
          "dimension" -> dimension,
          "metric" -> preparation.space.metric.name,
          "recipe" -> recipe,
          "files" -> Index_Format.data_files
            .map(f => f -> file_hash(directory + Path.basic(f)))
            .toMap
        )
      )
  }


  /** session builds **/

  // What determines the Isabelle build of an index.
  sealed case class Build_Request(
    sessions: List[String],
    timeout_scale: Double,
    session_options: Map[String, List[String]],
    jobs: Int,
    no_build: Boolean
  ) {
    def options: Options = Options.init() + ("timeout_scale=" + timeout_scale)
  }

  sealed case class Built(sessions: List[String], unbuilt: Obj, ids: Obj)

  // A session that fails, or is cancelled after a failed ancestor, is left out and reported;
  // the remaining sessions are indexed. Build ids identify the builds that were indexed.
  def build_sessions(request: Build_Request, afp: Path, progress: Progress): Built = {
    val updates = request.session_options.view.mapValues(_.map(Options.Spec.make)).toMap
    val results = Build.build(
      request.options,
      selection = Sessions.Selection(sessions = request.sessions),
      afp_root = Some(afp),
      max_jobs = Some(request.jobs),
      no_build = request.no_build,
      augment_options = name => updates.getOrElse(name, Nil),
      progress = progress
    )
    val ok = results.sessions_ok.toSet
    val (built, unbuilt) = request.sessions.partition(ok)
    val reasons = unbuilt.map { session =>
      session ->
        (if (request.no_build) "not built"
         else if (results.sessions(session) && results.cancelled(session)) "cancelled"
         else "failed")
    }
    for ((reason, sessions) <- reasons.groupBy(_._2).toList.sortBy(_._1))
      progress.echo_warning("Not indexed, " + reason + " (" + sessions.size + "): " +
        commas(sessions.map(_._1)))
    if (built.isEmpty) error("No selected session is built")
    val store = results.store
    val ids = built.map { session =>
      session -> using(store.open_database(session)) { db =>
        store.read_build(db, session).map(_.uuid).getOrElse("")
      }
    }
    Built(built, reasons.toMap, ids.toMap)
  }


  /** shared FindFacts sources **/

  // One FindFacts database serves all corpus builds of this user. It is re-indexed only when
  // the indexed sessions or their builds change, and each build exports the blocks it needs,
  // so builds share the database but never read it while it is re-indexed.
  val source_database = "isasearch"

  private def with_sources_lock[A](progress: Progress)(body: => A): A = {
    val lock_file = Isabelle_System.make_directory(home) + Path.basic("find_facts.lock")
    using(
      java.nio.channels.FileChannel.open(lock_file.java_path,
        java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.WRITE).nn
    ) { channel =>
      val lock = proper_value(channel.tryLock()).getOrElse {
        progress.echo("Waiting for another build to release the FindFacts sources ...")
        channel.lock().nn
      }
      try { body } finally { lock.release() }
    }
  }

  def export_sources(
    options: Options,
    afp: Path,
    built: Built,
    queries: List[(Corpus_Kind, String)],
    target: Path,
    progress: Progress
  ): Unit =
    with_sources_lock(progress) {
      val state = home + Path.basic("find_facts.json")
      val current: Obj = Map("database" -> source_database, "builds" -> built.ids)
      if (state.is_file && canonical(read(state)) == canonical(current))
        progress.echo("FindFacts index is current for " + built.sessions.size + " sessions")
      else {
        state.file.delete()
        Find_Facts.find_facts_index(
          options + ("find_facts_database_name=" + source_database),
          built.sessions,
          afp_root = Some(afp),
          browser_info = false,
          progress = progress
        )
        write(state, current)
      }
      using(Solr.init(Find_Facts.solr_data_dir).open_database(source_database)) { db =>
        for ((kind, query) <- queries) {
          using(Files.newBufferedWriter(sources(target, kind).java_path).nn) { out =>
            Find_Facts.private_data.stream_blocks(db, query, blocks =>
              for (block <- blocks) {
                out.write(JSON.Format(source(block)))
                out.newLine()
              })
          }
        }
      }
    }

  private def sources(target: Path, kind: Corpus_Kind): Path =
    target + Path.basic(kind.name + ".jsonl")

  private def read_sources[A](target: Path, kind: Corpus_Kind)(f: Iterator[Obj] => A): A =
    using(Files.newBufferedReader(sources(target, kind).java_path).nn) { in =>
      f(Iterator.continually(in.readLine()).takeWhile(_ != null).map(line =>
        obj(JSON.parse(line.nn))))
    }


  /** build and publication **/

  private def build_locked(
    config: Config,
    name: String,
    request: Build_Request,
    build: () => Built,
    progress: Progress,
    afp: Path,
    recipe: Obj,
    inference: Inference.Client,
    workspace: Path
  ): Path = {
    val output =
      Isabelle_System.make_directory(workspace + Path.basic("export-" + UUID.random_string()))
    val exported =
      Isabelle_System.make_directory(workspace + Path.basic("sources-" + UUID.random_string()))
    val preparation = new Preparation(config, afp, recipe, inference)
    val executor = Executors.newFixedThreadPool(config.positive("llm_concurrency", 1)).nn
    try {
      val sources = provenance(afp, progress)
      inference.generate("Reply with OK.", role = Model_Role.Document, health = true)
      inference.embed(List("IsaSearch embedding readiness check"), preparation.space)
      val built = build()
      val defaults = read(component + Path.explode("etc/corpus_defaults.json"))
      val queries = Index.kinds.map { kind =>
        kind -> config.string(kind.query_key, str(defaults, kind.query_key))
      }
      export_sources(request.options, afp, built, queries, exported, progress)
      val corpora = Index.kinds.flatMap { kind =>
        read_sources(exported, kind) { blocks =>
          write_corpus(blocks, kind, preparation, executor, config, name, recipe, output, progress)
        }
      }
      write(
        output + Path.basic(Index_Format.manifest),
        Map(
          "format" -> Index_Format.name,
          "version" -> Index_Format.version,
          "corpora" -> corpora,
          "provenance" -> (sources ++ Map(
            "source" -> "scala",
            "sessions" -> built.sessions,
            "unbuilt_sessions" -> built.unbuilt
          ))
        )
      )
      Index.import_index(output, name, progress)
    }
    finally {
      executor.shutdownNow()
      Isabelle_System.rm_tree(output)
      Isabelle_System.rm_tree(exported)
    }
  }
}
