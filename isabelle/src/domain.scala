/*  Title:      IsaSearch/isabelle/src/domain.scala

Application choices and external format names.
*/

package isabelle.isasearch


import isabelle._


/** external names **/

trait Named_Value {
  def name: String

  override def toString: String = name
}


object Named_Value {
  def parse[A <: Named_Value](values: Iterable[A], name: String, description: String): A =
    values.find(_.name == name).getOrElse(error("Unknown " + description + ": " + quote(name)))
}


/** corpora and inference **/

enum Corpus_Kind(val name: String, val query_key: String, val describe_key: String)
    extends Named_Value {
  case Theorems extends Corpus_Kind("theorems", "solr_query", "describe")
  case Definitions
      extends Corpus_Kind("definitions", "solr_query_definitions", "describe_definition")
}

object Corpus_Kind {
  def parse(name: String): Corpus_Kind = Named_Value.parse(values.toList, name, "corpus kind")
}

enum Distance_Metric(val name: String, val solr_name: String) extends Named_Value {
  case Cosine extends Distance_Metric("cosine", "cosine")
  case Squared_Euclidean extends Distance_Metric("l2", "euclidean")
}

object Distance_Metric {
  def parse(name: String): Distance_Metric =
    Named_Value.parse(values.toList, name, "distance metric")
}

enum Inference_Backend(val name: String) extends Named_Value {
  case Disabled extends Inference_Backend("none")
  case OpenAI extends Inference_Backend("openai")
  case Ollama extends Inference_Backend("ollama")
  case LlamaCpp extends Inference_Backend("llamacpp")
}

object Inference_Backend {
  def parse(name: String): Inference_Backend =
    Named_Value.parse(values.toList, name, "inference backend")
}

enum Model_Role(val name: String) extends Named_Value {
  case Document extends Model_Role("document")
  case Query extends Model_Role("query")
}

// The model endpoints of a configuration. Each has settings of its own: NAME_base_url, and for
// its API key NAME_api_key_file, NAME_api_key_env or NAME_api_key, so that a key goes to its
// endpoint only.
enum Endpoint(val name: String, val default_url: String = "") extends Named_Value {
  case OpenAI extends Endpoint("openai")
  case OpenAI_Embedding extends Endpoint("openai_embedding")
  case Ollama extends Endpoint("ollama", "http://localhost:11434")
  case LlamaCpp extends Endpoint("llamacpp")
  case LlamaCpp_Document extends Endpoint("llamacpp_document")

  def url: String = name + "_base_url"
  def key_file: String = name + "_api_key_file"
  def key_env: String = name + "_api_key_env"
  def key: String = name + "_api_key"
  def key_settings: List[String] = List(key_file, key_env, key)
}


/** query strategies **/

enum Query_Mode {
  case Original, Expanded, Combined

  def expands: Boolean = this != Original

  def combine(original: String, expanded: String): String = this match {
    case Original => original
    case Expanded => expanded
    case Combined => original + "\n\n" + expanded
  }
}

enum Benchmark_Strategy(val name: String, val metadata: Boolean, val mode: Query_Mode)
    extends Named_Value {
  case Baseline extends Benchmark_Strategy("baseline", false, Query_Mode.Original)
  case Expanded extends Benchmark_Strategy("R", false, Query_Mode.Expanded)
  case Combined extends Benchmark_Strategy("UR", false, Query_Mode.Combined)
  case Metadata extends Benchmark_Strategy("M", true, Query_Mode.Original)
  case Metadata_Expanded extends Benchmark_Strategy("MR", true, Query_Mode.Expanded)
  case Metadata_Combined extends Benchmark_Strategy("MUR", true, Query_Mode.Combined)
}

object Benchmark_Strategy {
  def parse(name: String): Benchmark_Strategy =
    Named_Value.parse(values.toList, name, "benchmark strategy")
}


/** search filters **/

// The part of the corpus a document comes from: the Isabelle distribution or the AFP.
enum Search_Source(val name: String) extends Named_Value {
  case All extends Search_Source("all")
  case Distribution extends Search_Source("distribution")
  case AFP extends Search_Source("afp")

  def distribution: Boolean = this != AFP
  def afp: Boolean = this != Distribution
}

object Search_Source {
  def parse(name: String): Search_Source = Named_Value.parse(values.toList, name, "source")
}

// The documents a search considers. The index selects them by source and AFP entry (`entries`
// restricts the AFP part; None admits every entry) before its nearest-neighbour search; the
// session and the tokens a statement must mention are checked on the nearest documents.
case class Search_Filter(
  source: Search_Source = Search_Source.All,
  entries: Option[Set[String]] = None,
  sessions: Option[Set[String]] = None,
  mentions: List[String] = Nil
) {
  if (!source.afp && entries.nonEmpty) error("AFP entries of a search of the distribution")
  if (entries.exists(_.contains(""))) error("Empty AFP entry name")
  if (mentions.exists(m => m.isEmpty || m.exists(Character.isWhitespace)))
    error("Mentioned tokens must be non-empty and without spaces")

  def admits(record: Data.Obj): Boolean =
    sessions.forall(_.contains(Data.str(record, "session"))) && {
      lazy val statement = Text_Preparation.statement(Data.str(record, "src"))
      mentions.forall(Text_Preparation.mentions(statement, _))
    }
}


/** duplicate evidence **/

enum Duplicate_Tier(val name: String) extends Named_Value {
  case Near_Exact extends Duplicate_Tier("near-exact")
  case Likely extends Duplicate_Tier("likely")
  case Possible extends Duplicate_Tier("possible")
}

enum Verdict(val name: String) extends Named_Value {
  case Duplicate extends Verdict("DUPLICATE")
  case Variant extends Verdict("VARIANT")
  case Related extends Verdict("RELATED")
  case Different extends Verdict("DIFFERENT")
  case Unknown extends Verdict("UNKNOWN")
}


/** embedding contract **/

case class Embedding_Space(
  recipe: Data.Obj,
  metric: Distance_Metric,
  dimension: Option[Int] = None
) {
  val model: String = Data.str(recipe, "model")
  val max_characters: Int = JSON
    .int_default(recipe, "max_characters", 0)
    .filter(_ >= 0)
    .getOrElse(error("Invalid embedding character limit"))

  def validate(vector: Array[Float]): Unit =
    Data.validate(vector, dimension.getOrElse(vector.length), metric)
}


/** persistent format **/

object Prompt {
  val Begin = "<BEGIN>"
  val End = "<END>"
  val Embed = "embed"
  val Retrieve = "retrieve"
  val Expand = "search_refine"
  val Judge = "duplicate_judge"
}

object Index_Format {
  val name = "isasearch"
  val version = 1
  val manifest = "manifest.json"
  val documents = "documents.jsonl"
  val vectors = "vectors.f32"
  val data_files = List(documents, vectors)
  // Optional per corpus: inputs with their vectors from the embedder of the index.
  val references = "reference_embeddings"
  // In shipped generations only: the Lucene version and the checksums of their files.
  val generation = "generation"
}

enum Export_Format(val name: String) extends Named_Value {
  case Generation extends Export_Format("generation")
  case Interchange extends Export_Format("interchange")
}

object Export_Format {
  def parse(name: String): Export_Format = Named_Value.parse(values.toList, name, "export format")
}


/** editors **/

// The Isabelle front-ends that the website opens the local file of a result in, at a line:
// each reuses its running window (Isabelle/jEdit only with an edit server, i.e. the JVM
// property isabelle.jedit_server as in Isabelle's application bundles) or starts a new one.
enum Isabelle_Editor(val name: String, val title: String) extends Named_Value {
  case JEdit extends Isabelle_Editor("jedit", "Isabelle/jEdit")
  case VSCode extends Isabelle_Editor("vscode", "Isabelle/VSCode")

  def command(isabelle: String, file: String, line: Option[Int]): String = this match {
    case JEdit => isabelle + " jedit -n " + file + line.map(n => " +line:" + n).getOrElse("")
    case VSCode => isabelle + " vscode -n -- --goto " + file + line.map(n => ":" + n).getOrElse("")
  }
}

object Isabelle_Editor {
  def parse(name: String): Isabelle_Editor = Named_Value.parse(values.toList, name, "editor")

  def list(s: String): List[Isabelle_Editor] = space_explode(',', s).map(Library.trim_string)
    .filter(_.nonEmpty).map(parse).distinct
}


/** command-line tools **/

enum Tool_Command(val name: String) extends Named_Value {
  case Import extends Tool_Command("import")
  case Index extends Tool_Command("index")
  case Package_Index extends Tool_Command("index_build")
  case Export extends Tool_Command("export")
  case Prune extends Tool_Command("prune")
  case Search extends Tool_Command("search")
  case Serve extends Tool_Command("server")
  case Duplicates extends Tool_Command("duplicates")
  case Benchmark extends Tool_Command("benchmark")
  case Compare extends Tool_Command("compare")
  case Test extends Tool_Command("test")
  case Integration_Test extends Tool_Command("integration_test")

  // Tools that embed queries, and so fall back to the default configuration without -c.
  def searches: Boolean = this == Search || this == Serve || this == Duplicates || this == Benchmark
}

object Tool_Command {
  def parse(name: String): Tool_Command = Named_Value.parse(values.toList, name, "IsaSearch tool")
}
