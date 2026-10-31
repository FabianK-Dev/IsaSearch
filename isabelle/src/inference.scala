/*  Title:      IsaSearch/isabelle/src/inference.scala

HTTP inference clients for user-managed model servers.
*/

package isabelle.isasearch


import isabelle._

import java.net.URI
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.time.Duration


object Inference {
  import Data._


  /** results **/

  case class Failure(message: String) extends RuntimeException(message)

  // A truncated completion was cut off at max_tokens on every attempt.
  case class Completion(
    text: String,
    duration: Double,
    elapsed: Double,
    cached: Boolean,
    truncated: Boolean = false
  )


  /** inference client **/

  class Client(val config: Config, store: Path = home) {

    /* HTTP requests */

    private val http = HttpClient
      .newBuilder().nn
      .connectTimeout(Duration.ofSeconds(config.positive("inference_connect_timeout", 10))).nn
      .build().nn

    // A key file (Isabelle path syntax, e.g. $ISASEARCH_HOME_USER/api_key) keeps the key out of
    // the environment of other processes; it takes precedence over a variable and a literal.
    def key: String = {
      val file = config.string("openai_api_key_file")
      val env = config.string("openai_api_key_env")
      if (file.nonEmpty) {
        val path = config.path("openai_api_key_file", "")
        if (!path.is_file) throw Failure("Missing API key file: " + path.implode)
        proper_string(Library.trim_line(File.read(path)))
          .getOrElse(throw Failure("Empty API key file: " + path.implode))
      }
      else if (env.nonEmpty)
        proper_string(System.getenv(env))
          .getOrElse(throw Failure("Missing API key environment variable: " + env))
      else config.string("openai_api_key")
    }

    private def call(url: String, body: Obj, attempts: Int, health: Boolean = false): Obj = {
      val uri = URI.create(url).nn
      if (!proper_string(uri.getScheme).exists(Set("http", "https")) || uri.getUserInfo != null)
        throw Failure("Inference URL must be HTTP(S) without embedded credentials")
      val timeout =
        if (health) config.positive("inference_health_timeout", 10)
        else config.positive("llm_request_timeout", 600)
      val builder = HttpRequest
        .newBuilder(uri).nn
        .timeout(Duration.ofSeconds(timeout)).nn
        .header("Content-Type", "application/json").nn
      if (key.nonEmpty) builder.header("Authorization", "Bearer " + key)
      val request = builder.POST(HttpRequest.BodyPublishers.ofString(JSON.Format(body))).nn.build()
      var last = "Inference request failed"
      var attempt = 0
      while (attempt < attempts) {
        try {
          val response = http.send(request, HttpResponse.BodyHandlers.ofString()).nn
          val code = response.statusCode()
          if (code >= 200 && code < 300) return obj(JSON.parse(response.body().nn))
          last = "Inference endpoint returned HTTP " + code
          if (!Set(429, 500, 502, 503, 504).contains(code)) throw Failure(last)
        }
        catch {
          case exn: Failure => throw exn
          case _: java.io.IOException => last = "Inference endpoint is unreachable or timed out"
          case ERROR(_) => last = "Malformed JSON from inference endpoint"
        }
        if (attempt + 1 < attempts) Thread.sleep(math.min(30000L, 1000L << attempt))
        attempt += 1
      }
      throw Failure(last)
    }

    private def endpoint(key: String, suffix: String, default: String = ""): String = {
      val base = config.string(key, default).stripSuffix("/")
      if (base.isEmpty) throw Failure("Configure " + key)
      base + suffix
    }


    /* persistent stores */

    // Keys cover exactly the inputs that determine an output, never endpoints or limits.
    private def stored(store: String, key: String, ext: String): Path =
      this.store + Path.explode(store) + Path.basic(key.take(2)) + Path.basic(key).ext(ext)


    /* embeddings */

    def embedding_model: String =
      config.string("openai_embedding_model", config.string("embedding_model"))

    private def embedding_backend: Inference_Backend =
      Inference_Backend.parse(config.string("embedding_backend", Inference_Backend.OpenAI.name))

    private def embedding_input(text: String, space: Embedding_Space): String =
      if (space.max_characters > 0) truncate(text, space.max_characters) else text

    def embed(texts: List[String], spec: Index.Spec): List[Array[Float]] = embed(texts, spec.space)

    def embed(texts: List[String], space: Embedding_Space): List[Array[Float]] = {
      val model = embedding_model
      if (model.isEmpty) throw Failure("Configure openai_embedding_model (or embedding_model)")
      if (model != space.model)
        throw Failure("Embedding model differs from index model: " + space.model)
      texts.map(embedding_input(_, space))
        .grouped(config.positive("openai_embedding_batch_size", 32))
        .flatMap { batch =>
          val vectors = embedding_backend match {
            case Inference_Backend.OpenAI | Inference_Backend.LlamaCpp =>
              val response = call(
                endpoint("openai_embedding_base_url", "/embeddings"),
                object_at(config.values, "embedding_extra_body") ++ Map(
                  "model" -> model,
                  "input" -> batch
                ),
                config.positive("embedding_attempts", 3)
              )
              val data =
                list(response.getOrElse("data", throw Failure("Missing embedding data"))).map(obj)
              val indices = data.map(r => num(r, "index", -1))
              if (indices.sorted != batch.indices.map(_.toDouble).toList)
                throw Failure("Invalid embedding response indices")
              data
                .sortBy(r => num(r, "index", -1))
                .map(r =>
                  list(
                    r.getOrElse("embedding", throw Failure("Missing vector in embedding response"))
                  ).map(number(_).toFloat).toArray
                )
            case Inference_Backend.Ollama =>
              val response = call(
                endpoint("ollama_base_url", "/api/embed", "http://localhost:11434"),
                object_at(config.values, "embedding_extra_body") ++ Map(
                  "model" -> model,
                  "input" -> batch,
                  "truncate" -> false
                ),
                config.positive("embedding_attempts", 3)
              )
              list(response.getOrElse("embeddings", throw Failure("Missing embeddings")))
                .map(v => list(v).map(number(_).toFloat).toArray)
            case other =>
              throw Failure(
                "Unsupported embedding backend: " + other + ". Serve the model through an HTTP endpoint."
              )
          }
          if (vectors.size != batch.size) throw Failure("Embedding response count mismatch")
          vectors.foreach(space.validate)
          vectors
        }
        .toList
    }

    // Embeds only texts without a stored vector, so an interrupted build resumes.
    def embed_stored(texts: List[String], space: Embedding_Space): List[Array[Float]] = {
      val paths = texts.map { text =>
        val key = canonical(Map(
          "backend" -> embedding_backend.name,
          "model" -> embedding_model,
          "extra_body" -> object_at(config.values, "embedding_extra_body"),
          "input" -> embedding_input(text, space)
        ))
        stored("embeddings", hash(key), "f32")
      }
      val missing = texts.zip(paths).filterNot(_._2.is_file).distinctBy(_._2)
      embed(missing.map(_._1), space).zip(missing).foreach { case (vector, (_, path)) =>
        write_bytes(path, Bytes(bytes(vector)))
      }
      paths.map { path =>
        val vector = floats(Bytes.read(path).make_array)
        space.validate(vector)
        vector
      }
    }


    /* generation */

    def llm_backend: Inference_Backend =
      Inference_Backend.parse(config.string("llm_backend", Inference_Backend.Disabled.name))

    def model(role: Model_Role): String =
      config.string(llm_backend.name + "_" + role.name + "_model")

    def configured(role: Model_Role): Boolean =
      llm_backend != Inference_Backend.Disabled && model(role).nonEmpty

    private def request(prompt: String, role: Model_Role, health: Boolean): (String, Obj) = {
      if (!configured(role)) throw Failure("No " + role + " LLM is configured")
      val sampling = object_at(config.values, "sampling_parameters")
      val common = Map[String, JSON.T](
        "temperature" -> num(sampling, "temperature", 0),
        "top_p" -> num(sampling, "top_p", 1)
      ) ++
        sampling
          .filter { case (k, _) => Set("stop", "min_p", "top_k").contains(k) }
          .filterNot { case (k, v) => k == "top_k" && number(v) < 0 }
      val tokens = if (health) 32 else num(sampling, "max_tokens", 512).toInt
      llm_backend match {
        case Inference_Backend.OpenAI =>
          (
            endpoint("openai_base_url", "/chat/completions"),
            common ++ object_at(config.values, "openai_extra_body") ++
              Map(
                "model" -> model(role),
                "messages" -> List(Map("role" -> "user", "content" -> prompt)),
                "max_tokens" -> tokens,
                "stream" -> false
              )
          )
        case Inference_Backend.Ollama =>
          (
            endpoint("ollama_base_url", "/api/generate", "http://localhost:11434"),
            Map(
              "model" -> model(role),
              "prompt" -> prompt,
              "stream" -> false,
              "options" -> (common ++ object_at(config.values, "ollama_options"))
                .updated("num_predict", tokens)
            )
          )
        case Inference_Backend.LlamaCpp =>
          val baseKey =
            if (role == Model_Role.Document && config.string("llamacpp_document_base_url").nonEmpty)
              "llamacpp_document_base_url"
            else "llamacpp_base_url"
          (
            endpoint(baseKey, "/completion"),
            common ++ object_at(config.values, "llamacpp_extra_body") ++ Map(
              "prompt" -> prompt,
              "n_predict" -> tokens,
              "stream" -> false
            )
          )
        case other => throw Failure("Unsupported LLM backend: " + other)
      }
    }

    // The text of a completion, and whether it was cut off at max_tokens.
    private def completion_text(response: Obj): (String, Boolean) = {
      val (text, truncated) = llm_backend match {
        case Inference_Backend.OpenAI =>
          val choice = list(response.getOrElse("choices", Nil)).headOption
            .map(obj)
            .getOrElse(throw Failure("Missing completion choices"))
          (str(object_at(choice, "message"), "content"), str(choice, "finish_reason") == "length")
        case Inference_Backend.Ollama =>
          (str(response, "response"), str(response, "done_reason") == "length")
        case _ =>
          (str(response, "content"), bool(response, "truncated"))
      }
      if (marked(text).isEmpty)
        throw Failure(
          if (truncated) "Truncated completion without content; increase max_tokens"
          else "Empty LLM completion; check model and thinking settings")
      (text, truncated)
    }

    private def output_path(role: Model_Role, body: Obj): Path =
      stored("llm_cache", hash(canonical(Map("model" -> model(role), "body" -> body))), "json")

    // Stores an output produced elsewhere for the request this client would send.
    def store_output(prompt: String, role: Model_Role, text: String, source: String): Boolean = {
      val path = output_path(role, request(prompt, role, false)._2)
      if (path.is_file) false
      else {
        write(path, Map("text" -> text, "source" -> source))
        true
      }
    }

    def generate(
      prompt: String,
      role: Model_Role = Model_Role.Query,
      health: Boolean = false,
      cached: Boolean = config.boolean("enable_llm_output_cache", true),
      accept_truncated: Boolean = false
    ): Completion = {
      val (url, body) = request(prompt, role, health)
      val start = System.nanoTime()
      val cache = output_path(role, body)
      val useCache = !health && cached
      if (useCache && cache.is_file) {
        val saved = read(cache)
        return Completion(
          str(saved, "text"),
          num(saved, "duration", 0),
          (System.nanoTime() - start) / 1e9,
          true,
          truncated = bool(saved, "truncated")
        )
      }
      val attempts = if (health) 1 else config.positive("llm_attempts", 3)
      var text = ""
      // As in Python, a completion cut off at max_tokens on every attempt is still accepted
      // where its text is better than none (corpus descriptions), and reported as truncated.
      var truncated_text = ""
      var failure: Option[Failure] = None
      var attempt = 0
      while (attempt < attempts && text.isEmpty) {
        // Python's generate_with_retries changes temperature after a failed completion.
        val retry_body =
          if (attempt == 0) body
          else if (llm_backend == Inference_Backend.Ollama)
            body.updated("options", object_at(body, "options").updated("temperature", 0.3))
          else body.updated("temperature", 0.3)
        try {
          val response = call(url, retry_body, 1, health = health)
          completion_text(response) match {
            case (complete, false) => text = complete
            case (partial, true) =>
              truncated_text = partial
              failure = Some(Failure("Truncated completion; increase max_tokens"))
          }
        }
        catch {
          case exn: Failure => failure = Some(exn)
          case ERROR(message) => failure = Some(Failure(message))
        }
        attempt += 1
        if (text.isEmpty && attempt < attempts)
          Thread.sleep(math.min(30000L, 1000L << (attempt - 1)))
      }
      val truncated = text.isEmpty && accept_truncated && truncated_text.nonEmpty
      if (truncated) text = truncated_text
      if (text.isEmpty) throw failure.getOrElse(Failure("Empty LLM completion"))
      val elapsed = (System.nanoTime() - start) / 1e9
      if (useCache) {
        write(cache, Map("text" -> text, "duration" -> elapsed) ++
          (if (truncated) Map("truncated" -> true) else Map.empty))
      }
      Completion(text, elapsed, elapsed, false, truncated = truncated)
    }


    /* embedding compatibility */

    def validate_reference(corpus: Index.Corpus): Unit = {
      val refs = corpus.all.take(2).toList
      val actual = embed(refs.map(r => str(r._2, "embedding_input")), corpus.spec)
      for (((n, _), v) <- refs.zip(actual)) {
        val expected = corpus.vector(n)
        val delta = distance(v, expected, Distance_Metric.Squared_Euclidean)
        val norm = expected.iterator.map(x => x.toDouble * x).sum
        if (delta / math.max(norm, 1e-20) > config.number("embedding_reference_tolerance", 0.001))
          throw Failure(
            "Embedding reference mismatch: model, pooling, normalization or preprocessing differs from index"
          )
      }
    }
  }
}
