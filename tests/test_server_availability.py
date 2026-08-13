"""
test_server_availability.py: Checks that the servers configured in config.json are actually
available and can serve what the configuration asks of them.

Unlike tests/test_openai_backends.py these tests talk to the real servers, thus they need the
servers to be running and the API key to be exported. They are skipped when config.json does not
select the "openai" backends, because the other backends start their servers themselves.

Run them with 'python3 -m unittest discover -s tests -t .' inside the root folder of the
repository, or alone with 'python3 -m unittest tests.test_server_availability -v'.
"""

import unittest

from src.bootstrap import load_config
from src.embeddings import (
    OPENAI_EMBEDDING_BACKEND,
    embedding_backend,
    ensure_embedding_backend,
    get_embedding_function,
)
from src.llm import (
    OPENAI_BACKEND,
    document_model_name,
    ensure_llm_backend,
    get_document_llm,
    get_llm,
    llm_backend,
    query_model_name,
)

# A worst case filler for the length check below: Isabelle source code with many mathematical
# symbols needs about two characters per token, whereas plain text needs about three. A text that
# is accepted at this density is accepted at any other.
SYMBOL_HEAVY_FILLER = "⟹∀∃≠⋀⟶λ∈⊆∩∪"


config = load_config()


@unittest.skipUnless(
    llm_backend(config) == OPENAI_BACKEND,
    "config['llm_backend'] is not '" + OPENAI_BACKEND + "'",
)
class LlmServerAvailabilityTest(unittest.TestCase):
    def test_server_is_reachable_and_serves_the_configured_models(self):
        # Reuses the same check that src/app.py runs on startup, so this test fails for exactly the
        # reasons a real run would fail: unreachable URL, missing API key or a rejected request.
        ensure_llm_backend(config)

    def test_query_model_generates_a_completion(self):
        answer = get_llm(config).generate(
            "Answer with the single word 'ready' and nothing else."
        )

        self.assertTrue(
            answer.strip(),
            "The query model '"
            + query_model_name(config)
            + "' at "
            + config["openai_base_url"]
            + " returned an empty completion.",
        )
        print(
            "\nQuery model '"
            + query_model_name(config)
            + "' answered: "
            + answer.strip()[:80]
        )

    def test_document_model_generates_a_completion(self):
        # The document model can be configured separately, thus it is checked separately.
        answer = get_document_llm(config).generate(
            "Answer with the single word 'ready' and nothing else."
        )

        self.assertTrue(
            answer.strip(),
            "The document model '"
            + document_model_name(config)
            + "' at "
            + config["openai_base_url"]
            + " returned an empty completion.",
        )


@unittest.skipUnless(
    embedding_backend(config) == OPENAI_EMBEDDING_BACKEND,
    "config['embedding_backend'] is not '" + OPENAI_EMBEDDING_BACKEND + "'",
)
class EmbeddingServerAvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.embedder = get_embedding_function(config)

    def test_server_is_reachable_and_returns_embeddings(self):
        # Reuses the same check that src/app.py runs on startup.
        ensure_embedding_backend(config)

    def test_embedding_dimension_is_stable(self):
        vectors = self.embedder(
            ["a theorem about prime numbers", "an unrelated statement"]
        )

        self.assertEqual(len(vectors), 2)
        self.assertGreater(len(vectors[0]), 0)
        self.assertEqual(
            len(vectors[0]),
            len(vectors[1]),
            "The embedding server returned vectors of different lengths.",
        )
        print(
            "\nEmbedding model '"
            + config["openai_embedding_model"]
            + "' returns "
            + str(len(vectors[0]))
            + " dimensional embeddings."
        )

    def test_server_accepts_a_document_of_the_configured_maximum_length(self):
        # This is the check that a plain reachability test misses: llama.cpp rejects an input that
        # does not fit into its physical batch instead of truncating it, and that error would only
        # surface once indexing reaches the first long theorem, aborting the whole run. If this
        # test fails, start the server with a bigger '-ub'/'-b' or lower the configured maximum.
        max_characters = self.embedder.max_characters
        document = (SYMBOL_HEAVY_FILLER * max_characters)[:max_characters]

        vectors = self.embedder([document])

        self.assertGreater(
            len(vectors[0]),
            0,
            "The embedding server did not accept a document of "
            + str(max_characters)
            + " characters, which is what config['openai_embedding_max_characters'] allows.",
        )

    def test_server_accepts_a_full_batch(self):
        # get_chromadb_collection embeds thousands of documents, which the embedding function sends
        # in batches of this size, so a server that only accepts smaller batches has to fail here.
        batch_size = self.embedder.batch_size

        vectors = self.embedder(["theorem number " + str(i) for i in range(batch_size)])

        self.assertEqual(len(vectors), batch_size)


if __name__ == "__main__":
    unittest.main()
