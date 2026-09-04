"""
test_openai_backends.py: Offline tests for the "openai" LLM and embedding backends.

These tests need no network and no GPU server: they run against the stub server in
tests/stub_openai_server.py, so they exercise the real client code without any external
dependency. Run them with 'python3 -m unittest discover -s tests -t .' inside the root folder of the
repository, or alone with 'python3 -m unittest tests.test_openai_backends -v'.

The tests that the configured servers are actually available live in
tests/test_server_availability.py.
"""

import os
import unittest
import warnings

from unittest import mock

import chromadb

from src import embeddings, llm
from src.openai_api import config_without_secrets, openai_api_key
from tests.helpers import temporary_folder
from tests.stub_openai_server import REJECTING_MODEL, StubOpenAIServer

API_KEY_ENV = "ISASEARCH_TEST_API_KEY"
API_KEY = "test-token"

SAMPLING_PARAMETERS = {
    "temperature": 0,
    "top_p": 1,
    "top_k": -1,
    "min_p": 0,
    "max_tokens": 256,
    "stop": ["<END>"],
}


class OpenAIBackendTestCase(unittest.TestCase):
    def setUp(self):
        self.server = StubOpenAIServer().start()
        self.addCleanup(self.server.stop)

        os.environ[API_KEY_ENV] = API_KEY
        self.addCleanup(lambda: os.environ.pop(API_KEY_ENV, None))

        self.config = {
            "llm_backend": "openai",
            "openai_base_url": self.server.base_url,
            "openai_document_model": "beaker_gemma4",
            "openai_query_model": "beaker_gemma4",
            "openai_api_key_env": API_KEY_ENV,
            "embedding_backend": "openai",
            "openai_embedding_base_url": self.server.base_url,
            "openai_embedding_model": "Qwen3-Embedding-4B",
            "openai_embedding_batch_size": 3,
            "sampling_parameters": dict(SAMPLING_PARAMETERS),
        }


class ApiKeyTest(OpenAIBackendTestCase):
    def test_key_is_read_from_the_configured_environment_variable(self):
        self.assertEqual(openai_api_key(self.config), API_KEY)

    def test_missing_environment_variable_fails_with_its_name(self):
        del os.environ[API_KEY_ENV]

        with self.assertRaises(RuntimeError) as error:
            openai_api_key(self.config)

        self.assertIn(API_KEY_ENV, str(error.exception))

    def test_no_key_configured_returns_none(self):
        self.assertIsNone(openai_api_key({}))

    def test_inline_key_is_used_as_a_fallback(self):
        self.assertEqual(openai_api_key({"openai_api_key": "inline"}), "inline")

    def test_inline_key_is_redacted_when_the_config_is_printed(self):
        redacted = config_without_secrets(
            {"openai_api_key": "inline", "api_port": 5001}
        )

        self.assertEqual(redacted["openai_api_key"], "<redacted>")
        self.assertEqual(redacted["api_port"], 5001)


class LlmBackendTest(OpenAIBackendTestCase):
    def test_model_names_come_from_the_openai_keys(self):
        self.assertEqual(llm.query_model_name(self.config), "beaker_gemma4")
        self.assertEqual(llm.document_model_name(self.config), "beaker_gemma4")

    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            llm.llm_backend({"llm_backend": "typo"})

    def test_ensure_checks_the_model_list_with_the_api_key(self):
        llm.ensure_llm_backend(self.config)

        request = self.server.requests_to("/v1/models")[0]
        self.assertEqual(request["authorization"], "Bearer " + API_KEY)

    def test_generate_sends_a_single_user_message(self):
        answer = llm.get_llm(self.config).generate("hello")

        self.assertEqual(answer, "<BEGIN>answer<END>")

        body = self.server.requests_to("/v1/chat/completions")[-1]["body"]
        self.assertEqual(body["model"], "beaker_gemma4")
        self.assertEqual(body["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(body["max_tokens"], 256)
        self.assertEqual(body["stop"], ["<END>"])
        self.assertEqual(body["min_p"], 0)
        # A negative top_k disables the sampler and must not be sent.
        self.assertNotIn("top_k", body)

    def test_positive_top_k_is_sent(self):
        self.config["sampling_parameters"]["top_k"] = 40

        llm.get_llm(self.config).generate("hello")

        self.assertEqual(
            self.server.requests_to("/v1/chat/completions")[-1]["body"]["top_k"], 40
        )

    # The settings that decide whether a local server is usable at all are the ones the OpenAI API
    # never standardised. Turning a reasoning model's thinking off is the one this project depends
    # on: with thinking on, the whole token budget goes into reasoning and the completion comes back
    # empty, so every description in the corpus is the empty string.
    def test_extra_body_is_merged_into_the_request(self):
        self.config["openai_extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": False}
        }

        llm.get_llm(self.config).generate("hello")

        body = self.server.requests_to("/v1/chat/completions")[-1]["body"]
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        # Merged next to the sampling parameters, not in place of them.
        self.assertEqual(
            body["max_tokens"], self.config["sampling_parameters"]["max_tokens"]
        )

    def test_extra_body_reaches_the_document_llm_as_well(self):
        # The descriptions are what an unusable setting silently ruins, so the document model has to
        # get it too, not only the query model.
        self.config["openai_extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": False}
        }

        llm.get_document_llm(self.config).generate("describe")

        body = self.server.requests_to("/v1/chat/completions")[-1]["body"]
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})

    def test_document_llm_uses_the_document_model(self):
        self.config["openai_document_model"] = "other-model"

        llm.get_document_llm(self.config).generate("describe")

        body = self.server.requests_to("/v1/chat/completions")[-1]["body"]
        self.assertEqual(body["model"], "other-model")

    def test_error_response_body_is_part_of_the_exception(self):
        model = llm.OpenAILLM(
            self.server.base_url,
            REJECTING_MODEL,
            llm.openai_options(self.config),
            API_KEY,
        )

        with self.assertRaises(RuntimeError) as error:
            model.generate("hello")

        self.assertIn("context size exceeded", str(error.exception))

    def test_unreachable_server_fails_with_its_url(self):
        self.config["openai_base_url"] = "http://127.0.0.1:9/v1"

        with self.assertRaises(RuntimeError) as error:
            llm.ensure_llm_backend(self.config)

        self.assertIn("127.0.0.1:9", str(error.exception))

    def test_other_backends_are_unchanged(self):
        config = {
            "llm_backend": "ollama",
            "ollama_base_url": "http://localhost:11434",
            "ollama_query_model": "phi3:mini",
            "ollama_document_model": "phi3.5",
            "sampling_parameters": dict(SAMPLING_PARAMETERS),
        }

        self.assertEqual(llm.query_model_name(config), "phi3:mini")
        self.assertEqual(llm.document_model_name(config), "phi3.5")
        self.assertIsInstance(llm.get_llm(config), llm.OllamaLLM)


class EmbeddingBackendTest(OpenAIBackendTestCase):
    def test_backend_defaults_to_the_local_one(self):
        self.assertEqual(
            embeddings.embedding_backend({}),
            embeddings.SENTENCE_TRANSFORMERS_EMBEDDING_BACKEND,
        )

    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            embeddings.embedding_backend({"embedding_backend": "typo"})

    def test_ensure_is_a_no_op_for_the_local_backend(self):
        self.assertIsNone(
            embeddings.ensure_embedding_backend(
                {"embedding_backend": "sentence_transformers"}
            )
        )

    def test_ensure_embeds_a_probe_with_the_api_key(self):
        embeddings.ensure_embedding_backend(self.config)

        request = self.server.requests_to("/v1/embeddings")[-1]
        self.assertEqual(request["authorization"], "Bearer " + API_KEY)
        self.assertEqual(request["body"]["model"], "Qwen3-Embedding-4B")

    def test_texts_are_sent_in_batches_and_stay_in_order(self):
        texts = ["a", "bb", "ccc", "dddd", "eeeee", "ffffff", "g"]

        vectors = embeddings.get_embedding_function(self.config)(texts)

        self.assertEqual(len(vectors), len(texts))
        # The stub encodes the length of each text as the first component of its embedding, so a
        # wrong order or a lost text shows up here.
        self.assertEqual([float(v[0]) for v in vectors], [float(len(t)) for t in texts])
        self.assertEqual(
            [
                len(r["body"]["input"])
                for r in self.server.requests_to("/v1/embeddings")
            ],
            [3, 3, 1],
        )

    def test_texts_are_truncated_to_the_configured_maximum(self):
        self.config["openai_embedding_max_characters"] = 10

        vectors = embeddings.get_embedding_function(self.config)(["y" * 500])

        self.assertEqual(float(vectors[0][0]), 10.0)

    def test_maximum_defaults_to_the_documented_value(self):
        self.assertEqual(
            embeddings.get_embedding_function(self.config).max_characters,
            embeddings.DEFAULT_EMBEDDING_MAX_CHARACTERS,
        )

    def test_transient_failures_are_retried(self):
        embedder = embeddings.get_embedding_function(self.config)
        self.server.transient_failures = 2

        vectors = embedder(["retry me"])

        self.assertEqual(list(vectors[0]), [8.0, 0.0])
        self.assertEqual(len(self.server.requests_to("/v1/embeddings")), 3)

    def test_transient_failures_give_up_after_the_configured_attempts(self):
        embedder = embeddings.get_embedding_function(self.config)
        self.server.transient_failures = 99

        # Exhausting the real attempts would spend the full real-world patience of roughly twenty
        # minutes asleep, so the backoff is capped at zero for this test.
        with mock.patch.object(embeddings, "EMBEDDING_BACKOFF_CAP", 0):
            with self.assertRaises(RuntimeError) as error:
                embedder(["always fails"])

        self.assertIn("model is loading", str(error.exception))
        self.assertEqual(
            len(self.server.requests_to("/v1/embeddings")),
            embeddings.EMBEDDING_ATTEMPTS,
        )

    def test_permanent_failures_are_not_retried(self):
        self.config["openai_embedding_model"] = REJECTING_MODEL

        with self.assertRaises(RuntimeError) as error:
            embeddings.get_embedding_function(self.config)(["x"])

        # Retrying an input that the server rejects as too large would only delay the failure.
        self.assertEqual(len(self.server.requests_to("/v1/embeddings")), 1)
        self.assertIn("input is too large", str(error.exception))
        # The message has to name the longest input, because that is what usually caused it.
        self.assertIn("with up to 1 characters", str(error.exception))

    def test_the_persisted_config_carries_no_api_key(self):
        config = embeddings.get_embedding_function(self.config).get_config()

        self.assertNotIn("api_key", config)
        self.assertEqual(config["model_name"], "Qwen3-Embedding-4B")


class ChromaDbCollectionTest(OpenAIBackendTestCase):
    """ChromaDB requires more of an embedding function than being callable, and it is the only
    component that persists it, so the whole lifecycle is exercised against a real collection."""

    def setUp(self):
        super().setUp()
        self.chroma_db_path = temporary_folder(self)

    def open_collection(self):
        client = chromadb.PersistentClient(path=self.chroma_db_path)
        return client.get_or_create_collection(
            "afp_docs",
            embedding_function=embeddings.get_embedding_function(self.config),
            metadata={"hnsw:space": "cosine"},
        )

    def test_collection_can_be_created_filled_queried_and_reopened(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            collection = self.open_collection()
            collection.add(documents=["first theorem"], ids=["first"])

            reopened = self.open_collection()
            reopened.add(documents=["second theorem"], ids=["second"])
            results = reopened.query(query_texts=["a query"], n_results=2)

        self.assertEqual(reopened.count(), 2)
        self.assertEqual(len(results["ids"][0]), 2)
        self.assertEqual(reopened.metadata, {"hnsw:space": "cosine"})
        self.assertEqual(
            [
                str(w.message)
                for w in caught
                if issubclass(w.category, DeprecationWarning)
            ],
            [],
        )

    def test_the_distance_function_is_asked_of_the_embedding_function(self):
        # get_chromadb_collection reads the distance function off the embedder rather than off the
        # configured backend name, so an embedder that does not ask for one - the local
        # sentence-transformers backend - leaves ChromaDB's default and with it every collection
        # that was built before untouched.
        self.assertEqual(
            embeddings.OpenAIEmbeddingFunction.collection_metadata,
            {"hnsw:space": "cosine"},
        )
        self.assertIsNone(getattr(object(), "collection_metadata", None))


# A completion stopped at max_tokens is cut off mid-sentence and would otherwise be embedded in
# that state without anything saying so, which is how ~5% of a real run's descriptions ended up
# damaged before anyone noticed.
class TruncatedCompletionTest(OpenAIBackendTestCase):
    def model(self):
        return llm.get_llm(self.config)

    def test_a_completion_that_finishes_is_returned(self):
        self.assertEqual(self.model().generate("prompt"), "<BEGIN>answer<END>")

    def test_a_completion_cut_off_at_max_tokens_is_reported(self):
        self.server.truncated_completions = 1

        with self.assertRaises(llm.TruncatedCompletionError) as raised:
            self.model().generate("prompt")

        self.assertIn("max_tokens", str(raised.exception))
        # The text is carried on the error, so a caller can keep it rather than lose it.
        self.assertEqual(raised.exception.output, "<BEGIN>cut off here")

    def test_a_retry_can_still_produce_a_whole_completion(self):
        self.server.truncated_completions = 1

        self.assertEqual(
            llm.generate_with_retries(self.model(), "prompt"), "<BEGIN>answer<END>"
        )

    def test_a_completion_that_is_always_cut_off_is_still_returned(self):
        self.server.truncated_completions = llm.LLM_ATTEMPTS

        with self.assertRaises(llm.TruncatedCompletionError) as raised:
            llm.generate_with_retries(self.model(), "prompt")

        self.assertEqual(raised.exception.output, "<BEGIN>cut off here")


if __name__ == "__main__":
    unittest.main()
