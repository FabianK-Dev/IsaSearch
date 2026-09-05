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
}


/** command-line tools **/

enum Tool_Command(val name: String) extends Named_Value {
  case Import extends Tool_Command("import")
  case Index extends Tool_Command("index")
  case Package_Index extends Tool_Command("index_build")
  case Search extends Tool_Command("search")
  case Serve extends Tool_Command("server")
  case Duplicates extends Tool_Command("duplicates")
  case Benchmark extends Tool_Command("benchmark")
  case Test extends Tool_Command("test")
}

object Tool_Command {
  def parse(name: String): Tool_Command = Named_Value.parse(values.toList, name, "IsaSearch tool")
}
