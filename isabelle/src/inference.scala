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

  case class Completion(text: String, duration: Double, elapsed: Double, cached: Boolean)


  /** inference client **/

  class Client(val config: Config) {

    /* HTTP requests */

    private val http = HttpClient
      .newBuilder()
      .connectTimeout(Duration.ofSeconds(config.positive("inference_connect_timeout", 10)))
      .build()

    def key: String = {
      val env = config.string("openai_api_key_env")
      if (env.nonEmpty)
        Option(System.getenv(env))
          .filter(_.nonEmpty)
          .getOrElse(throw Failure("Missing API key environment variable: " + env))
      else config.string("openai_api_key")
    }

    private def call(url: String, body: Obj, attempts: Int, health: Boolean = false): Obj = {
      val uri = URI.create(url)
      if (!Set("http", "https").contains(uri.getScheme) || uri.getUserInfo != null)
        throw Failure("Inference URL must be HTTP(S) without embedded credentials")
      val timeout =
        if (health) config.positive("inference_health_timeout", 10)
        else config.positive("llm_request_timeout", 600)
      val builder = HttpRequest
        .newBuilder(uri)
        .timeout(Duration.ofSeconds(timeout))
        .header("Content-Type", "application/json")
      if (key.nonEmpty) builder.header("Authorization", "Bearer " + key)
      val request = builder.POST(HttpRequest.BodyPublishers.ofString(JSON.Format(body))).build()
      var last = "Inference request failed"
      var attempt = 0
      while (attempt < attempts) {
        try {
          val response = http.send(request, HttpResponse.BodyHandlers.ofString())
          val code = response.statusCode()
          if (code >= 200 && code < 300) return obj(JSON.parse(response.body()))
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


    /* embeddings */

    def embedding_model: String =
      config.string("openai_embedding_model", config.string("embedding_model"))

    def embed(texts: List[String], spec: Index.Spec): List[Array[Float]] = embed(texts, spec.space)

    def embed(texts: List[String], space: Embedding_Space): List[Array[Float]] = {
      val model = embedding_model
      if (model.isEmpty) throw Failure("Configure openai_embedding_model (or embedding_model)")
      if (model != space.model)
        throw Failure("Embedding model differs from index model: " + space.model)
      val max = space.max_characters
      val prepared = texts.map(s => if (max > 0) truncate(s, max) else s)
      prepared
        .grouped(config.positive("openai_embedding_batch_size", 32))
        .flatMap { batch =>
          val backend = Inference_Backend.parse(
            config.string("embedding_backend", Inference_Backend.OpenAI.name)
          )
          val vectors = backend match {
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

    def generate(
      prompt: String,
      role: Model_Role = Model_Role.Query,
      health: Boolean = false
    ): Completion = {
      val (url, body) = request(prompt, role, health)
      val start = System.nanoTime()
      val cacheKey = hash(canonical(Map("model" -> model(role), "url" -> url, "body" -> body)))
      val cache = home + Path.explode("llm_cache/" + cacheKey + ".json")
      val useCache = !health && config.boolean("enable_llm_output_cache", true)
      if (useCache && cache.is_file) {
        val saved = read(cache)
        return Completion(
          str(saved, "text"),
          num(saved, "duration", 0),
          (System.nanoTime() - start) / 1e9,
          true
        )
      }
      val response =
        call(url, body, if (health) 1 else config.positive("llm_attempts", 3), health = health)
      val text = llm_backend match {
        case Inference_Backend.OpenAI =>
          val choice = list(response.getOrElse("choices", Nil)).headOption
            .map(obj)
            .getOrElse(throw Failure("Missing completion choices"))
          if (str(choice, "finish_reason") == "length")
            throw Failure("Truncated completion; increase max_tokens")
          str(object_at(choice, "message"), "content")
        case Inference_Backend.Ollama =>
          if (str(response, "done_reason") == "length")
            throw Failure("Truncated completion; increase max_tokens")
          str(response, "response")
        case _ =>
          if (bool(response, "truncated"))
            throw Failure("Truncated completion; increase max_tokens")
          str(response, "content")
      }
      if (marked(text).isEmpty)
        throw Failure("Empty LLM completion; check model and thinking settings")
      val elapsed = (System.nanoTime() - start) / 1e9
      if (useCache) write(cache, Map("text" -> text, "duration" -> elapsed))
      Completion(text, elapsed, elapsed, false)
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
