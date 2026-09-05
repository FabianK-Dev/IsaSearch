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

    val expanded = requested.flatMap {
      case "all" => structure.imports_topological_order.filter(n => structure(n).is_afp || hol(n))
      case "all-AFP" => structure.imports_topological_order.filter(n => structure(n).is_afp)
      case name =>
        if (!structure.defined(name)) error("Unknown Isabelle session: " + name) else List(name)
    }
    val excluded = strings(config.values, "isabelle_excluded_sessions").toSet
    expanded.distinct.filterNot(excluded)
  }


  /** source metadata **/

  def metadata(root: Path, entry: String): Obj = {
    if (entry.isEmpty) return Map.empty
    val file = root + Path.explode("metadata/entries/" + safe_name(entry) + ".toml")
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
    val roots = List(Path.explode("$AFP"), AFP.main_dir(), AFP.main_dir(afp))
    roots.map(_.squash.implode + "/").find(file.startsWith).map(file.stripPrefix)
  }

  def source_record(
    block: Find_Facts.Block,
    relative: Option[String],
    meta: Obj,
    config: Config
  ): Obj = {
    val e = relative.map(_.takeWhile(_ != '/')).getOrElse("")
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
      "thms" -> block.thms,
      "entry" -> e,
      "entry_date" -> str(meta, "date"),
      "metadata" -> meta,
      "theory_url" -> (config
        .string("isabelle_remote_theory_url", "https://isabelle.in.tum.de/library")
        .stripSuffix("/") + "/" + block.url_path.implode),
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
                           .stripSuffix("/") + "/" + relative.get + "#L" + block.start_line)
    )
  }


  /** build configuration **/

  def run(
    config: Config,
    name: String,
    supplied: List[String],
    no_build: Boolean,
    progress: Progress
  ): Path = {
    val afp = afp_root
    val options = Options.init() + ("timeout_scale=" + config.number("isabelle_timeout_scale", 1))
    val selected = sessions(config, options, afp, supplied)
    if (selected.isEmpty) error("No sessions remain after exclusions")
    progress.echo("AFP: " + afp.implode + "; sessions: " + selected.mkString(", "))
    val excluded = strings(config.values, "isabelle_excluded_sessions")
    if (excluded.nonEmpty) progress.echo("Excluded sessions: " + excluded.mkString(", "))
    val prompt_base = config.path("prompts_folder", "../prompts/qwen3-gemma")
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
    val fingerprint = hash(
      canonical(
        Map(
          "config" -> config.public_values,
          "recipe" -> recipe,
          "sessions" -> selected,
          "afp" -> afp.implode
        )
      )
    )
    val workspace = Isabelle_System.make_directory(home + Path.explode("build/" + safe_name(name)))
    using(
      java.nio.channels.FileChannel.open(
        (workspace + Path.basic("build.lock")).java_path,
        java.nio.file.StandardOpenOption.CREATE,
        java.nio.file.StandardOpenOption.WRITE
      )
    ) { channel =>
      val lock = channel.tryLock()
      if (lock == null) error("Another corpus build is running for " + name)
      try {
        build_locked(
          config,
          name,
          selected,
          no_build,
          progress,
          afp,
          options,
          recipe,
          inference,
          fingerprint,
          workspace
        )
      }
      finally { lock.release() }
    }
  }


  /** resumable inference **/

  private class Preparation(
    config: Config,
    afp: Path,
    recipe: Obj,
    cache: Path,
    inference: Inference.Client
  ) {
    val space = Embedding_Space(
      recipe,
      Distance_Metric.parse(config.string("distance_metric", Distance_Metric.Cosine.name))
    )
    private val metadata_cache = scala.collection.concurrent.TrieMap.empty[String, Obj]
    private val prompts = object_at(recipe, "prompts")

    def apply(block: Find_Facts.Block, kind: Corpus_Kind): (Obj, Array[Float]) = {
      val relative = afp_relative(block.file, afp)
      val entry_name = relative.map(_.takeWhile(_ != '/')).getOrElse("")
      val meta = metadata_cache.getOrElseUpdate(entry_name, metadata(afp, entry_name))
      val record = source_record(block, relative, meta, config)
      val cache_path = cache + Path.basic(hash(kind.name + block.id + canonical(record)) + ".json")
      if (cache_path.is_file) {
        val saved = read(cache_path)
        val vector = list(saved("vector")).map(number(_).toFloat).toArray
        space.validate(vector)
        (object_at(saved, "document"), vector)
      }
      else {
        val description_path = cache_path.ext("description")
        val artifact =
          if (description_path.is_file) read(description_path)
          else {
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
            val prompt = template(
              prompt_template,
              Map(
                "theorem_content" -> truncate(
                  Text_Preparation.strip_proof(block.src),
                  config.positive("theorem_max_length", 3000)
                ).trim,
                "title" -> (if (title.isEmpty) "-- no title --" else title),
                "abstract" -> (if (abstract_excerpt.isEmpty) "-- no abstract --"
                               else abstract_excerpt)
              )
            )
            val completion = inference.generate(prompt, role = Model_Role.Document)
            val checksum = new java.util.zip.Adler32()
            checksum.update(block.src.getBytes(java.nio.charset.StandardCharsets.UTF_8))
            val result = Map(
              "llm_description" -> completion.text,
              "prompt" -> prompt,
              "zlib.adler32_checksum" -> checksum.getValue
            )
            write(description_path, result)
            result
          }
        val description = marked(str(artifact, "llm_description"))
        val embedding = template(
          str(prompts, Prompt.Embed),
          Map("doc_src" -> (description.trim + "\n\n" + block.src.trim))
        )
        val vector = inference.embed(List(embedding), space).head
        val doc = record ++ Map(
          "kind" -> kind.name,
          "checksum" -> artifact("zlib.adler32_checksum"),
          "llm_description" -> description,
          "embedding_input" -> embedding,
          "description_artifact" -> artifact
        )
        write(cache_path, Map("document" -> doc, "vector" -> vector.toList.map(_.toDouble)))
        (doc, vector)
      }
    }
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
    blocks: Iterator[Find_Facts.Block],
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
    using(Files.newBufferedWriter((directory + Path.basic(Index_Format.documents)).java_path)) { docs =>
      using(Files.newOutputStream((directory + Path.basic(Index_Format.vectors)).java_path)) { vectors =>
        blocks.grouped(config.positive("openai_embedding_batch_size", 32)).foreach { batch =>
          val tasks = batch.map { block =>
            executor.submit(new Callable[(Obj, Array[Float])] {
              def call(): (Obj, Array[Float]) = preparation(block, kind)
            })
          }
          tasks.foreach { task =>
            val (doc, vector) = try { task.get() }
            catch {
              case exn: java.util.concurrent.ExecutionException => throw exn.getCause
            }
            if (!seen.add(str(doc, "id"))) error("Duplicate source ID")
            identities += identity(doc)
            if (dimension == 0) dimension = vector.length
            validate(vector, dimension, preparation.space.metric)
            docs.write(JSON.Format(doc))
            docs.newLine()
            vectors.write(bytes(vector))
          }
          progress.echo("Prepared " + seen.size + " " + kind)
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


  /** build and publication **/

  private def build_locked(
    config: Config,
    name: String,
    selected: List[String],
    no_build: Boolean,
    progress: Progress,
    afp: Path,
    options: Options,
    recipe: Obj,
    inference: Inference.Client,
    fingerprint: String,
    workspace: Path
  ): Path = {
    val output =
      Isabelle_System.make_directory(workspace + Path.basic("export-" + UUID.random_string()))
    val cache = Isabelle_System.make_directory(workspace + Path.basic(fingerprint))
    val preparation = new Preparation(config, afp, recipe, cache, inference)
    val executor = Executors.newFixedThreadPool(config.positive("llm_concurrency", 1))
    try {
      inference.generate("Reply with OK.", role = Model_Role.Document, health = true)
      inference.embed(List("IsaSearch embedding readiness check"), preparation.space)
      val source_name = "isasearch_" + name
      val ff_options = options + ("find_facts_database_name=" + source_name)
      if (!no_build) {
        val result = Build.build(
          options,
          selection = Sessions.Selection(sessions = selected),
          afp_root = Some(afp),
          progress = progress
        )
        if (!result.ok) error("Isabelle session build failed")
      }
      Find_Facts.find_facts_index(
        ff_options,
        selected,
        afp_root = Some(afp),
        browser_info = false,
        progress = progress
      )
      val defaults = read(component + Path.explode("etc/corpus_defaults.json"))
      val source_system = Solr.init(Find_Facts.solr_data_dir)
      val corpora = using(source_system.open_database(source_name)) { db =>
        Index.kinds.flatMap { kind =>
          val query = config.string(kind.query_key, str(defaults, kind.query_key))
          var result: Option[Obj] = None
          Find_Facts.private_data.stream_blocks(
            db,
            query,
            blocks => {
              result = write_corpus(
                blocks,
                kind,
                preparation,
                executor,
                config,
                name,
                recipe,
                output,
                progress
              )
            }
          )
          result
        }
      }
      write(
        output + Path.basic(Index_Format.manifest),
        Map(
          "format" -> Index_Format.name,
          "version" -> Index_Format.version,
          "corpora" -> corpora,
          "provenance" -> Map(
            "source" -> "scala",
            "sessions" -> selected,
            "afp_version" -> Isabelle_System.getenv("AFP_VERSION"),
            "fingerprint" -> fingerprint
          )
        )
      )
      Index.import_index(output, name, progress)
    }
    finally {
      executor.shutdownNow()
      Isabelle_System.rm_tree(output)
    }
  }
}
