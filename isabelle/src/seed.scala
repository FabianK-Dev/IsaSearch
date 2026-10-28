/*  Title:      IsaSearch/isabelle/src/seed.scala

Seeding the description store from description artifacts of the Python implementation.
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


  /** description store **/

  // Descriptions are stored under the request this configuration sends for their prompt, so a
  // build reuses one exactly when it renders the same prompt for the same document model.
  def run(
    config: Config,
    artifacts: List[Path],
    progress: Progress,
    store: Path = home
  ): Unit = {
    if (artifacts.isEmpty) error("Specify description artifacts")
    val inference = new Inference.Client(config, store = store)
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
}
