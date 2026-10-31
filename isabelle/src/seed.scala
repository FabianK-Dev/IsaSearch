/*  Title:      IsaSearch/isabelle/src/seed.scala

Seeding the description and embedding stores from the Python implementation: description
artifacts and index exports.
*/

package isabelle.isasearch


import isabelle._

import com.fasterxml.jackson.core.{JsonFactory, JsonToken}


object Seed {
  import Data._


  /** artifact entries **/

  // An artifact is a JSON object of document IDs to objects with string fields, among them
  // "llm_description", "prompt" and "model". It is streamed: artifacts reach several hundred MB.
  def entries(artifact: Path)(f: Map[String, String] => Unit): Unit =
    using(new JsonFactory().createParser(artifact.file).nn) { parser =>
      def expect(token: JsonToken): Unit =
        if (parser.nextToken() != token) error("Malformed description artifact " + artifact)

      expect(JsonToken.START_OBJECT)
      while (parser.nextToken() == JsonToken.FIELD_NAME) {
        expect(JsonToken.START_OBJECT)
        var fields = Map.empty[String, String]
        while (parser.nextToken() == JsonToken.FIELD_NAME) {
          val key = parser.currentName().nn
          if (parser.nextToken() == JsonToken.VALUE_STRING) fields += key -> parser.getText.nn
          else parser.skipChildren()
        }
        f(fields)
      }
    }


  /** stores **/

  // Description artifacts seed the description store, index exports (interchange
  // directories) the embedding store.
  def run(
    config: Config,
    sources: List[Path],
    progress: Progress,
    store: Path = home
  ): Unit = {
    if (sources.isEmpty) error("Specify description artifacts or index exports")
    val inference = new Inference.Client(config, store = store)
    val (exports, artifacts) = sources.partition(_.is_dir)
    if (artifacts.nonEmpty) descriptions(inference, artifacts, progress)
    for (directory <- exports) embeddings(config, inference, directory, progress)
  }


  /** description store **/

  // Descriptions are stored under the request this configuration sends for their prompt, so a
  // build reuses one exactly when it renders the same prompt for the same document model.
  private def descriptions(
    inference: Inference.Client,
    artifacts: List[Path],
    progress: Progress
  ): Unit = {
    if (!inference.configured(Model_Role.Document))
      error("Configure the document LLM that produced the artifacts")
    val model = inference.model(Model_Role.Document)
    for (artifact <- artifacts) {
      var stored, present, other_model, unusable = 0
      entries(artifact) { fields =>
        val text = fields.getOrElse("llm_description", "")
        val prompt = fields.getOrElse("prompt", "")
        if (!fields.get("model").contains(model)) other_model += 1
        else if (prompt.isEmpty || marked(text).isEmpty) unusable += 1
        else if (inference.store_output(prompt, Model_Role.Document, text, artifact.implode))
          stored += 1
        else present += 1
      }
      progress.echo(artifact.implode + ": " + stored + " stored, " + present +
        " already present, " + other_model + " from another or unknown model, " + unusable +
        " without prompt or description")
    }
  }


  /** embedding store **/

  // An index export holds the exact embedding input of each document with its vector, e.g. the
  // Python index exported by src.export_index. A vector is stored under the key that builds of
  // this configuration look up for that input, provided the export was embedded by the same
  // backend and model with the same character limit.
  private def embeddings(
    config: Config,
    inference: Inference.Client,
    directory: Path,
    progress: Progress
  ): Unit = {
    val manifest = read(directory + Path.basic(Index_Format.manifest))
    val space = Embedding_Space(
      Map("max_characters" -> Corpus_Build.max_characters(config)), Corpus_Build.metric(config))
    for (spec <- list(manifest.getOrElse("corpora", Nil)).map(c => Index.Spec(obj(c)))) {
      val label = directory.implode + " " + spec.kind
      val backend = str(spec.recipe, "backend", "openai")
      if (spec.space.model != inference.embedding_model ||
          backend != inference.embedding_backend.name ||
          spec.space.max_characters != space.max_characters) {
        progress.echo(label + ": skipped, embedded by " + backend + " " + spec.space.model +
          " with " + spec.space.max_characters + " characters")
      }
      else {
        val input = directory + Path.basic(spec.kind.name)
        var stored, present = 0
        using(new java.io.DataInputStream(new java.io.BufferedInputStream(
            java.nio.file.Files.newInputStream((input + Path.basic(Index_Format.vectors)).java_path)
          ))) { vectors =>
          using(scala.io.Source.fromFile((input + Path.basic(Index_Format.documents)).file,
              "UTF-8")) { documents =>
            for (line <- documents.getLines()) {
              val vector = new Array[Byte](spec.dimension * java.lang.Float.BYTES)
              vectors.readFully(vector)
              val text = str(obj(JSON.parse(line)), "embedding_input")
              if (inference.store_embedding(text, space, floats(vector))) stored += 1
              else present += 1
            }
          }
        }
        progress.echo(label + ": " + stored + " vectors stored, " + present + " already present")
      }
    }
  }
}
