/*  Title:      IsaSearch/isabelle/src/index.scala

Persistent vector indexes: Solr writers and read-only Lucene snapshots.
*/

package isabelle.isasearch


import isabelle._

import isabelle.find_facts.Solr
import java.io.{BufferedInputStream, DataInputStream}
import java.nio.file.{Files, StandardCopyOption}
import java.util.concurrent.Executors
import org.apache.lucene.codecs.KnnVectorsFormat
import org.apache.lucene.codecs.lucene912.Lucene912Codec
import org.apache.lucene.codecs.lucene99.Lucene99HnswVectorsFormat
import org.apache.lucene.store.FSDirectory
import org.apache.lucene.index.{
  DirectoryReader,
  DocValues,
  IndexWriter,
  IndexWriterConfig,
  ReaderUtil
}
import org.apache.lucene.search.{
  IndexSearcher,
  KnnFloatVectorQuery,
  TermQuery,
  TopDocs,
  ScoreDoc,
  BooleanQuery,
  BooleanClause,
  MatchAllDocsQuery
}
import org.apache.lucene.index.Term
import org.apache.solr.index.NoMergePolicyFactory


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

  object Schema {
    val hnsw_max_connections: Int = Lucene99HnswVectorsFormat.DEFAULT_MAX_CONN
    val hnsw_beam_width: Int = Lucene99HnswVectorsFormat.DEFAULT_BEAM_WIDTH
  }

  class Schema(dim: Int, metric: Distance_Metric) extends Solr.Data("isasearch") {
    val id = Solr.Field("id", Solr.Type.string).make_unique_key
    val entry = Solr.Field("entry", Solr.Type.string)
    // Records are read as stored fields only: doc values would limit them to 32766 bytes.
    val record =
      Solr.Field("record", Solr.Type.string, Solr.Column_Wise(false) ::: Solr.Indexed(false))
    val vector = Solr.Field(
      "vector",
      Solr.Type(
        "vector_type",
        "DenseVectorField",
        List(
          "vectorDimension" -> dim.toString,
          "similarityFunction" -> metric.solr_name,
          "hnswMaxConnections" -> Schema.hnsw_max_connections.toString,
          "hnswBeamWidth" -> Schema.hnsw_beam_width.toString
        )
      ),
      Solr.Stored(false)
    )
    val fields = Solr.Fields(id, entry, record, vector)

    // Segments are merged once, by merge_segments: a background merge of HNSW graphs can outlast
    // the time Solr allows for closing a core.
    override def solr_config: XML.Body = super.solr_config.map {
      case XML.Elem(m, body) =>
        val no_merges = XML.Elem(
          Markup("mergePolicyFactory", List("class" -> classOf[NoMergePolicyFactory].getName.nn)),
          Nil
        )
        XML.Elem(
          m,
          body ::: List(
            Solr.Class("codecFactory", "SchemaCodecFactory"),
            XML.elem("indexConfig", List(no_merges))
          )
        )
      case x => x
    }
  }


  /** Lucene segments **/

  def lucene_index(root: Path, kind: Corpus_Kind): Path =
    root + Path.explode("solr/" + kind + "/data/index")

  // A search visits the HNSW graph of every segment, and each batch of an import commits a
  // segment of its own, which Solr leaves unmerged. A generation is read-only once published, so
  // its segments are merged into one beforehand, with the HNSW parameters of the schema.
  def merge_segments(index: Path): Unit = {
    val workers = Multithreading.max_threads()
    val executor = Executors.newFixedThreadPool(workers).nn
    try {
      val vectors = new Lucene99HnswVectorsFormat(
        Schema.hnsw_max_connections, Schema.hnsw_beam_width, workers, executor)
      val codec = new Lucene912Codec {
        override def getKnnVectorsFormatForField(field: String): KnnVectorsFormat = vectors
      }
      val config = new IndexWriterConfig()
        .setOpenMode(IndexWriterConfig.OpenMode.APPEND).nn
        .setCodec(codec).nn
      using(FSDirectory.open(index.java_path).nn) { dir =>
        using(new IndexWriter(dir, config)) { writer =>
          writer.forceMerge(1)
          writer.commit()
        }
      }
    }
    finally { executor.shutdown() }
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
        progress.echo("Merging the segments of " + spec.kind + " ...")
        merge_segments(lucene_index(staging, spec.kind))
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
    private val dir = FSDirectory.open(lucene_index(root, spec.kind).java_path).nn
    private val reader = DirectoryReader.open(dir).nn
    if (reader.numDocs() != spec.count) {
      reader.close()
      dir.close()
      error("Index document count disagrees with manifest")
    }
    private val searcher = new IndexSearcher(reader)

    def segments: Int = reader.leaves().nn.size

    def close(): Unit = {
      reader.close()
      dir.close()
    }

    private def stored(n: Int, fields: String*) =
      reader.storedFields().nn.document(n, java.util.Set.of(fields*)).nn

    // IDs and vectors of documents come from doc values and vector values, which the HNSW search
    // reads as well, rather than from the large stored fields. Both are read per segment in
    // document order.
    private def vectors(docs: List[Int]): List[(Int, String, Array[Float])] = {
      val leaves = reader.leaves().nn
      docs.sorted.groupBy(ReaderUtil.subIndex(_, leaves)).toList.sortBy(_._1).flatMap {
        case (i, ns) =>
          val leaf = leaves.get(i).nn
          val values =
            proper_value(leaf.reader().nn.getFloatVectorValues("vector"))
              .getOrElse(error("Missing vectors"))
          val ids = DocValues.getSorted(leaf.reader(), "id").nn
          ns.map { n =>
            val d = n - leaf.docBase
            if (values.advance(d) != d || !ids.advanceExact(d)) error("Missing vector or ID")
            (n, ids.lookupOrd(ids.ordValue()).nn.utf8ToString().nn, values.vectorValue().nn.clone())
          }
      }
    }

    private def hits(top: TopDocs | Null): List[ScoreDoc] =
      top.nn.scoreDocs.nn.toList.map(_.nn)

    def record(n: Int): Obj = {
      val json = proper_value(stored(n, "record").get("record")).getOrElse(error("Missing record"))
      obj(JSON.parse(json))
    }

    def vector(n: Int): Array[Float] = vectors(List(n)).head._3

    def all: Iterator[(Int, Obj)] = (0 until reader.maxDoc()).iterator.map(i => i -> record(i))

    def get(id: String): Option[(Int, Obj)] =
      hits(searcher.search(new TermQuery(new Term("id", id)), 1)).headOption
        .map(hit => hit.doc -> record(hit.doc))

    // The HNSW graph misses some nearest neighbours: up to `candidates` approximate hits are
    // ranked by exact distance, and only the best `limit` records are read.
    def search(v: Array[Float], limit: Int, candidates: Int, exclude: String = ""): List[Obj] = {
      validate(v, spec.dimension, spec.metric)
      val k = math.min(math.max(limit, candidates), spec.count)
      val query =
        if (exclude.isEmpty) new KnnFloatVectorQuery("vector", v, k)
        else {
          val filter = new BooleanQuery.Builder()
            .add(new MatchAllDocsQuery(), BooleanClause.Occur.MUST).nn
            .add(new TermQuery(new Term("entry", exclude)), BooleanClause.Occur.MUST_NOT).nn
            .build()
          new KnnFloatVectorQuery("vector", v, k, filter)
        }
      vectors(hits(searcher.search(query, k)).map(_.doc))
        .map { case (n, id, vector) => (distance(v, vector, spec.metric), id, n) }
        .sortBy { case (d, id, _) => (d, id) }
        .take(limit)
        .map { case (d, _, n) => record(n).updated("distance", d) }
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
