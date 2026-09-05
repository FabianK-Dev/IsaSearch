/*  Title:      IsaSearch/isabelle/src/index.scala

Persistent vector indexes: Solr writers and read-only Lucene snapshots.
*/

package isabelle.isasearch


import isabelle._

import isabelle.find_facts.Solr
import java.io.{BufferedInputStream, DataInputStream}
import java.nio.file.{Files, StandardCopyOption}
import org.apache.lucene.store.FSDirectory
import org.apache.lucene.index.DirectoryReader
import org.apache.lucene.search.{
  IndexSearcher,
  KnnFloatVectorQuery,
  TermQuery,
  BooleanQuery,
  BooleanClause,
  MatchAllDocsQuery
}
import org.apache.lucene.index.Term


object Index {
  import Data._


  /** corpus specifications **/

  val kinds = Corpus_Kind.values.toList

  case class Spec(json: Obj) {
    val kind = Corpus_Kind.parse(str(json, "kind"))
    val dimension =
      JSON.int(json, "dimension").getOrElse(error("Expected integer vector dimension"))
    val count = JSON.int(json, "count").getOrElse(error("Expected integer document count"))
    val metric = Distance_Metric.parse(str(json, "metric"))
    if (dimension <= 0 || count <= 0) error("Empty or invalid corpus: " + kind)
    validate(Array.fill(dimension)(1.0f), dimension, metric)
    val recipe = object_at(json, "recipe")
    val space = Embedding_Space(recipe, metric, Some(dimension))
    val prompts = object_at(recipe, "prompts")
    if (space.model.isEmpty) error("Missing embedding model identity")
    JSON.bool(recipe, "add_metadata").getOrElse(error("Missing metadata variant"))
    List(Prompt.Embed, Prompt.Retrieve).foreach { key =>
      if (str(prompts, key).isEmpty) error("Missing prompt: " + key)
    }
  }

  // Avoid eager evaluation of a default error in lookups.
  def prompt(spec: Spec, key: String): String = {
    val name =
      if (spec.kind == Corpus_Kind.Definitions && spec.prompts.contains(key + "_definitions"))
        key + "_definitions"
      else key
    spec.prompts.get(name).map(_.asInstanceOf[String]).getOrElse(error("Missing prompt: " + name))
  }


  /** Solr schema **/

  class Schema(dim: Int, metric: Distance_Metric) extends Solr.Data("isasearch") {
    val id = Solr.Field("id", Solr.Type.string).make_unique_key
    val entry = Solr.Field("entry", Solr.Type.string)
    val record = Solr.Field("record", Solr.Type.string, List("indexed" -> "false"))
    val raw = Solr.Field("raw_vector", Solr.Type.bytes, List("indexed" -> "false"))
    val vector = Solr.Field(
      "vector",
      Solr.Type(
        "vector_type",
        "DenseVectorField",
        List(
          "vectorDimension" -> dim.toString,
          "similarityFunction" -> metric.solr_name
        )
      ),
      List("stored" -> "false")
    )
    val fields = Solr.Fields(id, entry, record, raw, vector)

    override def solr_config: XML.Body = super.solr_config.map {
      case XML.Elem(m, body) =>
        XML.Elem(m, body :+ Solr.Class("codecFactory", "SchemaCodecFactory"))
      case x => x
    }
  }


  /** manifest validation **/

  def specs(manifest: Obj): List[Spec] = {
    if (
      str(manifest, "format") != Index_Format.name || num(
        manifest,
        "version",
        0
      ) != Index_Format.version
    )
      error("Unsupported IsaSearch interchange format/version")
    val result = list(manifest.getOrElse("corpora", Nil)).map(x => Spec(obj(x)))
    if (result.isEmpty || result.map(_.kind).distinct.size != result.size)
      error("Missing or duplicate corpora")
    result
  }


  /** index generations **/

  def location(name: String): Path = home + Path.explode("indexes/" + safe_name(name))

  def current(name: String): Path = {
    val pointer = location(name) + Path.basic("current.json")
    if (!pointer.is_file) resolve(name)
    if (!pointer.is_file) error("No built index '" + name + "'. Import or build it first.")
    location(name) + Path.basic(safe_name(str(read(pointer), "generation")))
  }

  def publish(name: String, staging: Path): Path = {
    val parent = Isabelle_System.make_directory(location(name))
    val generation = "generation-" + UUID.random_string()
    val target = parent + Path.basic(generation)
    Files.move(staging.java_path, target.java_path, StandardCopyOption.ATOMIC_MOVE)
    write(parent + Path.basic("current.json"), Map("generation" -> generation))
    target
  }


  /** interchange import **/

  def import_index(source: Path, name: String, progress: Progress = new Progress): Path = {
    val manifest = read(source + Path.basic(Index_Format.manifest))
    val corpora = specs(manifest)
    val parent = Isabelle_System.make_directory(location(name))
    val staging = parent + Path.basic("staging-" + UUID.random_string())
    Isabelle_System.make_directory(staging)
    try {
      val system = Solr.init(staging + Path.basic("solr"))
      for (spec <- corpora) {
        val input = source + Path.basic(spec.kind.name)
        for (file <- Index_Format.data_files) {
          val expected = str(object_at(spec.json, "files"), file)
          if (expected.isEmpty || file_hash(input + Path.basic(file)) != expected)
            error("Checksum mismatch: " + spec.kind + "/" + file)
        }
        if (Files.size((input + Path.basic(Index_Format.vectors)).java_path) !=
            spec.count.toLong * spec.dimension * java.lang.Float.BYTES)
          error("Vector file length mismatch")
        val schema = new Schema(spec.dimension, spec.metric)
        val seen = scala.collection.mutable.HashSet.empty[String]
        using(system.init_database(spec.kind.name, schema)) { db =>
          using(
            new DataInputStream(
              new BufferedInputStream(
                Files.newInputStream((input + Path.basic(Index_Format.vectors)).java_path)
              )
            )
          ) { in =>
            using(
              scala.io.Source.fromFile((input + Path.basic(Index_Format.documents)).file, "UTF-8")
            ) { text =>
              text.getLines().grouped(256).foreach { lines =>
                val batch = lines.map { line =>
                  val record = obj(JSON.parse(line))
                  val id = str(record, "id")
                  if (id.isEmpty || !seen.add(id))
                    error("Missing or duplicate document ID: " + id)
                  for (key <- List("src", "llm_description", "embedding_input"))
                    if (!record.contains(key) || !record(key).isInstanceOf[String])
                      error("Missing document field: " + key)
                  if (str(record, "kind") != spec.kind.name) error("Document kind mismatch")
                  val checksum = new java.util.zip.Adler32()
                  checksum.update(
                    str(record, "src").getBytes(java.nio.charset.StandardCharsets.UTF_8)
                  )
                  if (num(record, "checksum", -1).toLong != checksum.getValue)
                    error("Source checksum mismatch: " + id)
                  val raw = new Array[Byte](spec.dimension * java.lang.Float.BYTES)
                  in.readFully(raw)
                  val vector = floats(raw)
                  validate(vector, spec.dimension, spec.metric)
                  (doc: Solr.Document) => {
                    doc.string(schema.id) = id
                    doc.string(schema.entry) = str(record, "entry", entry(id))
                    doc.string(schema.record) = JSON.Format(record)
                    doc.bytes(schema.raw) = Bytes(raw)
                    doc.double(schema.vector) = vector.toList.map(_.toDouble)
                  }
                }
                db.transaction { db.execute_batch_insert(batch) }
                progress.echo(
                  "Imported " + seen.size + "/" + spec.count + " " + spec.kind,
                  verbose = true
                )
              }
            }
            if (seen.size != spec.count || in.read() != -1) error("Document/vector count mismatch")
          }
        }
      }
      write(staging + Path.basic(Index_Format.manifest), manifest)
      val result = publish(name, staging)
      progress.echo("Published index " + name)
      result
    }
    catch {
      case exn: Throwable =>
        Isabelle_System.rm_tree(staging)
        throw exn
    }
  }


  /** distributed indexes **/

  def resolve(name: String): Unit = {
    val candidates = Path
      .split(Isabelle_System.getenv("ISASEARCH_INDEXES"))
      .filter(_.drop_ext.file_name == name)
    if (candidates.size > 1) error("Multiple registered indexes named " + name)
    candidates.headOption.foreach { archive =>
      val parent = Isabelle_System.make_directory(location(name))
      val staging =
        Isabelle_System.make_directory(parent + Path.basic("staging-" + UUID.random_string()))
      try {
        File_Store.database_extract(archive, staging, compress_cache = Compress.Cache.make())
        using(new Snapshot(staging)) { _ => () }
        publish(name, staging)
      }
      catch {
        case exn: Throwable =>
          Isabelle_System.rm_tree(staging)
          throw exn
      }
    }
  }

  def package_index(name: String, target: Path): Path = {
    val source = current(name)
    val component = Components
      .Directory(
        target + Path.basic("isasearch_" + safe_name(name) + "-" + Date.Format.alt_date(Date.now()))
      )
      .create()
    val archive = Path.basic(name).db
    File_Store.make_database(
      component.path + archive,
      source,
      compress_options = Compress.Options_Zstd(level = 8),
      compress_cache = Compress.Cache.make()
    )
    component.write_settings(
      "\nISASEARCH_INDEXES=\"$ISASEARCH_INDEXES:$COMPONENT/" + archive.implode + "\"\n"
    )
    component.path
  }


  /** read-only search **/

  class Corpus(val root: Path, val spec: Spec) extends AutoCloseable {
    private val dir =
      FSDirectory.open((root + Path.explode("solr/" + spec.kind + "/data/index")).java_path)
    private val reader = DirectoryReader.open(dir)
    if (reader.numDocs() != spec.count) {
      reader.close()
      dir.close()
      error("Index document count disagrees with manifest")
    }
    private val searcher = new IndexSearcher(reader)

    def close(): Unit = {
      reader.close()
      dir.close()
    }

    def record(n: Int): Obj = obj(JSON.parse(reader.storedFields().document(n).get("record")))

    def vector(n: Int): Array[Float] = {
      val b = reader.storedFields().document(n).getBinaryValue("raw_vector")
      floats(java.util.Arrays.copyOfRange(b.bytes, b.offset, b.offset + b.length))
    }

    def all: Iterator[(Int, Obj)] = (0 until reader.maxDoc()).iterator.map(i => i -> record(i))

    def get(id: String): Option[(Int, Obj)] = searcher
      .search(new TermQuery(new Term("id", id)), 1)
      .scoreDocs
      .headOption
      .map(hit => hit.doc -> record(hit.doc))

    def search(v: Array[Float], limit: Int, exclude: String = ""): List[Obj] = {
      validate(v, spec.dimension, spec.metric)
      val filter =
        if (exclude.isEmpty) null
        else
          new BooleanQuery.Builder()
            .add(new MatchAllDocsQuery(), BooleanClause.Occur.MUST)
            .add(new TermQuery(new Term("entry", exclude)), BooleanClause.Occur.MUST_NOT)
            .build()
      val hits = searcher.search(
        new KnnFloatVectorQuery("vector", v, math.min(limit, spec.count), filter),
        math.min(limit, spec.count)
      )
      hits.scoreDocs.toList
        .map { hit =>
          record(hit.doc).updated("distance", distance(v, vector(hit.doc), spec.metric))
        }
        .sortBy(r => (num(r, "distance", 0), str(r, "id")))
    }
  }


  /** index snapshots **/

  class Snapshot(val root: Path) extends AutoCloseable {
    val manifest = read(root + Path.basic(Index_Format.manifest))
    val corpora = specs(manifest).map(s => s.kind -> new Corpus(root, s)).toMap

    def apply(kind: Corpus_Kind): Corpus =
      corpora.getOrElse(kind, error("Corpus unavailable: " + kind))

    def close(): Unit = corpora.values.foreach(_.close())
  }
}
