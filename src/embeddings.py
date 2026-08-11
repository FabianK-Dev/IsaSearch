"""
embeddings.py: This file manages ChromaDB embeddings and semantic search with LLM-based query refinement and a caching mechanism.

Two embedding backends are supported and selected through config["embedding_backend"]:
- "sentence_transformers" (default): embeds locally with the sentence-transformers model
  configured at config["chroma_db_embedder"].
- "openai": embeds remotely through the /embeddings endpoint of any OpenAI compatible server
  (e.g. a llama-server running an embedding model on a GPU machine).

This file is the only place that knows about embedding backend specific configuration keys.
Other modules should use the backend agnostic helpers (get_embedding_function,
ensure_embedding_backend) instead.
"""

import os
import time
import torch
import chromadb
import requests

from tqdm import tqdm
from chromadb.api.types import EmbeddingFunction
from chromadb.utils import embedding_functions


from src.solr import docs_by_ids
from src.llm import save_llm_output_cache, query_model_name
from src.openai_api import openai_api_key, openai_headers, raise_for_status_with_body

SENTENCE_TRANSFORMERS_EMBEDDING_BACKEND = "sentence_transformers"
OPENAI_EMBEDDING_BACKEND = "openai"

SUPPORTED_EMBEDDING_BACKENDS = [
    SENTENCE_TRANSFORMERS_EMBEDDING_BACKEND,
    OPENAI_EMBEDDING_BACKEND,
]

# Number of attempts per embedding request before giving up, so that a single hiccup of the
# embedding server does not abort an indexing run that has already taken hours.
EMBEDDING_ATTEMPTS = 3

# HTTP status codes that are worth retrying, i.e. a busy or temporarily unavailable server. Every
# other error is permanent (e.g. an unknown model or an input that exceeds the batch size of the
# server), thus retrying it would only delay the inevitable failure.
RETRYABLE_STATUS_CODES = [429, 500, 502, 503, 504]

# Maximum number of characters per text that is sent to the embedding server. llama.cpp rejects an
# input that does not fit into a single physical batch instead of truncating it, and a theorem
# including its proof easily exceeds that limit, so without truncating here a single long theorem
# would abort every indexing run at the very same document.
# Isabelle source code tokenizes at roughly 3 characters per token, and at only about 2 for
# symbol-heavy theorems, thus 8000 characters can become close to 4000 tokens. The embedding server
# therefore has to be started with a physical batch size of at least 4096 (llama-server: '-ub 4096
# -b 4096'), which is far above its default of 512. Lower this value to embed with a smaller batch.
DEFAULT_EMBEDDING_MAX_CHARACTERS = 8000


# Raised for errors that are worth retrying, so that they can be told apart from permanent ones.
class RetryableEmbeddingError(RuntimeError):
    pass


# Returns the configured embedding backend and validates it, so that a typo fails early instead of
# silently falling back. Configurations without the key keep embedding locally as before.
def embedding_backend(config):
    backend = config.get("embedding_backend", SENTENCE_TRANSFORMERS_EMBEDDING_BACKEND)

    if backend not in SUPPORTED_EMBEDDING_BACKENDS:
        raise ValueError(
            "Unknown embedding backend '"
            + str(backend)
            + "' configured at config['embedding_backend']. Supported backends are "
            + ", ".join("'" + name + "'" for name in SUPPORTED_EMBEDDING_BACKENDS)
            + "."
        )

    return backend


# A ChromaDB embedding function that embeds through the /embeddings endpoint of an OpenAI compatible
# server. It has to subclass ChromaDB's EmbeddingFunction and implement name(), get_config() and
# build_from_config(), because get_or_create_collection() calls name() on the embedding function to
# compare it against the one persisted next to the collection. The parameter of __call__ has to be
# named 'input', because ChromaDB inspects its signature.
class OpenAIEmbeddingFunction(EmbeddingFunction):
    def __init__(
        self,
        base_url,
        model_name,
        batch_size,
        max_characters=DEFAULT_EMBEDDING_MAX_CHARACTERS,
        api_key=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_characters = max_characters
        self.headers = openai_headers(api_key)

    @staticmethod
    def name():
        # Must not collide with the names ChromaDB registers for its own embedding functions
        # (e.g. "openai"), because a persisted name is looked up in that registry.
        return "isasearch_openai"

    def get_config(self):
        # ChromaDB persists this config next to the collection, thus the API key is deliberately
        # not part of it and is always taken from the configuration instead.
        return {
            "base_url": self.base_url,
            "model_name": self.model_name,
            "batch_size": self.batch_size,
            "max_characters": self.max_characters,
        }

    # Only required so that ChromaDB does not treat this embedding function as a legacy one. The
    # embedding function is always passed explicitly, so ChromaDB never rebuilds it from its config.
    # Entries are read defensively, because ChromaDB also calls this for a config that was persisted
    # by an older version of this class, which then did not know all of the keys above.
    @staticmethod
    def build_from_config(config):
        return OpenAIEmbeddingFunction(
            config["base_url"],
            config["model_name"],
            config["batch_size"],
            config.get("max_characters", DEFAULT_EMBEDDING_MAX_CHARACTERS),
        )

    def embed_batch(self, texts):
        last_error = None
        # The longest input is part of every error message, because the most likely permanent error
        # is an input that does not fit into the batch size the server was started with.
        description = (
            "Embedding "
            + str(len(texts))
            + " document(s) with up to "
            + str(max(len(text) for text in texts) if texts else 0)
            + " characters at "
            + self.base_url
        )

        for attempt in range(EMBEDDING_ATTEMPTS):
            try:
                response = requests.post(
                    self.base_url + "/embeddings",
                    json={"model": self.model_name, "input": texts},
                    headers=self.headers,
                    timeout=600,
                )

                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise RetryableEmbeddingError(
                        description
                        + " failed with status code "
                        + str(response.status_code)
                        + ": "
                        + response.text
                    )

                # Permanent errors are raised from here and are deliberately not retried.
                raise_for_status_with_body(response, description)

                payload = response.json()

                if "data" not in payload:
                    raise RuntimeError(
                        description
                        + " returned a response without a 'data' entry: "
                        + response.text[:500]
                    )

                # The OpenAI API does not guarantee that the embeddings are returned in the order of
                # the inputs, thus they are sorted by their index before the vectors are extracted.
                return [
                    entry["embedding"]
                    for entry in sorted(
                        payload["data"], key=lambda entry: entry["index"]
                    )
                ]
            except (
                requests.RequestException,
                RetryableEmbeddingError,
                # A response body that cannot be parsed as JSON usually means a truncated transfer.
                ValueError,
            ) as exc:
                last_error = exc

                if attempt + 1 < EMBEDDING_ATTEMPTS:
                    # Exponential backoff, so that a server which is busy loading or swapping a
                    # model gets some time to recover before the next attempt.
                    backoff = 2**attempt
                    print(
                        "Embedding request to "
                        + self.base_url
                        + " failed ("
                        + str(exc)
                        + "). Retrying in "
                        + str(backoff)
                        + " second(s)..."
                    )
                    time.sleep(backoff)

        raise RuntimeError(
            description
            + " failed after "
            + str(EMBEDDING_ATTEMPTS)
            + " attempts: "
            + str(last_error)
            + " If the server rejects the input as too large, either start it with a bigger physical"
            + " batch size (llama-server: '-ub' and '-b') or lower"
            + " config['openai_embedding_max_characters']."
        )

    def __call__(self, input):
        embeddings = []

        # A document is the LLM description together with the untruncated theorem source code, which
        # can exceed what the server accepts within a single batch. Such an error is permanent, so a
        # single long theorem would abort every indexing run at the same document. The local
        # sentence-transformers backend truncates as well, just silently at the maximum sequence
        # length of its model.
        texts = [text[: self.max_characters] for text in input]

        # ChromaDB hands over all documents of a collection.add(...) call at once (5000 below), which
        # would exceed the batch and context limits of the embedding server, thus the texts are sent
        # in smaller batches. The progress bar is only shown for more than a single batch, so that
        # embedding a search query stays silent.
        for i in tqdm(
            range(0, len(texts), self.batch_size),
            disable=len(texts) <= self.batch_size,
        ):
            embeddings.extend(self.embed_batch(texts[i : i + self.batch_size]))

        return embeddings


# Returns the ChromaDB embedding function of the configured embedding backend. Note that the local
# sentence-transformers model is only loaded if that backend is actually configured.
def get_embedding_function(config):
    if embedding_backend(config) == OPENAI_EMBEDDING_BACKEND:
        print(
            "Using the OpenAI compatible embedding server at "
            + config["openai_embedding_base_url"]
            + "..."
        )
        return OpenAIEmbeddingFunction(
            config["openai_embedding_base_url"],
            config["openai_embedding_model"],
            config.get("openai_embedding_batch_size", 32),
            config.get(
                "openai_embedding_max_characters", DEFAULT_EMBEDDING_MAX_CHARACTERS
            ),
            openai_api_key(config),
        )

    print("Loading ChromaDB embedding function...")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        embedding_device = "mps"
    elif torch.cuda.is_available():
        embedding_device = "cuda"
    else:
        embedding_device = "cpu"

    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=config["chroma_db_embedder"],
        device=embedding_device,
    )


# Makes sure that the configured embedding backend is usable before any indexing starts, so that a
# wrong URL, a missing API key or an unknown model fails on startup and not hours into a run.
def ensure_embedding_backend(config):
    if embedding_backend(config) != OPENAI_EMBEDDING_BACKEND:
        return

    base_url = config["openai_embedding_base_url"]
    print("Checking OpenAI compatible embedding server at " + base_url + "...")

    # A server of this backend is never started automatically, because it usually runs on a
    # different machine. Embedding a single short text is the most reliable check, because it
    # exercises exactly the request that is used during indexing and searching.
    embeddings = get_embedding_function(config)(["IsaSearch embedding backend check"])

    # ChromaDB normalizes the returned vectors into NumPy arrays, whose truth value is ambiguous,
    # thus emptiness is checked through their length.
    if len(embeddings) == 0 or len(embeddings[0]) == 0:
        raise RuntimeError(
            "The embedding server at "
            + base_url
            + " did not return an embedding for the startup check."
        )

    print(
        "The embedding server at "
        + base_url
        + " is up and running and returns "
        + str(len(embeddings[0]))
        + " dimensional embeddings."
    )


# This method loads an existing or creates a new ChromaDB collection and embeds all documents that haven't been embedded, yet.
def get_chromadb_collection(config, prompts, document_index):
    embedder = get_embedding_function(config)

    # ChromaDB path
    if not os.path.exists(config["chroma_db_path"]):
        os.makedirs(config["chroma_db_path"])

    # ChromaDB client and collection
    chroma_db_path = config["chroma_db_path"] + "/chroma_db"
    print("Loading ChromaDB collection at path '" + chroma_db_path + "'...")

    # Embedding models that are served through an OpenAI compatible API (e.g. Qwen3-Embedding) are
    # trained for cosine similarity, whereas ChromaDB defaults to squared L2. Collections that
    # already exist keep their configured distance function, because ChromaDB ignores the metadata
    # of get_or_create_collection for them, thus existing collections stay untouched.
    collection_metadata = None
    if embedding_backend(config) == OPENAI_EMBEDDING_BACKEND:
        collection_metadata = {"hnsw:space": "cosine"}

    chroma_client = chromadb.PersistentClient(path=chroma_db_path)
    collection = chroma_client.get_or_create_collection(
        "afp_docs", embedding_function=embedder, metadata=collection_metadata
    )

    # Get set of all already existing document IDs (saved at the source key)
    existing = set()
    metadata_response = collection.get(include=["metadatas"])

    if "metadatas" in metadata_response and metadata_response["metadatas"] is not None:
        for item in metadata_response["metadatas"]:
            existing.add(item["source"])

    print("Preparing documents before adding to ChromaDB collection...")
    filtered_index = [doc_id for doc_id in document_index if doc_id not in existing]
    print(f"{len(filtered_index)} documents are still missing in ChromaDB collection.")

    # Documents will be embedded in batches of 5000 documents each.
    for i in range(0, len(filtered_index), 5000):
        doc_ids = filtered_index[i : i + 5000]
        print(f"Processing documents {i} to {i + len(doc_ids)}...")

        doc_embeddings = []
        metadatas = []

        for doc_id in doc_ids:
            doc = document_index[doc_id]
            # Append an instruction before the document string, which improves the search quality in zero-shot situations.
            doc_src = doc["llm_description"].strip() + "\n\n" + doc["src"].strip()
            embedding_str = prompts["embed"].format(doc_src=doc_src)

            doc_embeddings.append(embedding_str)
            metadatas.append({"source": doc["id"]})

        collection.add(documents=doc_embeddings, ids=doc_ids, metadatas=metadatas)

    return collection


# This search(...) method does the following:
# 1. If enabled, refine the search query using a LLM. If config["enable_llm_output_cache"] is enabled, it will use cached responses for cached search queries.
# 2. Combine the original search query and LLM-refined search query to search the ChromaDB collection for the top 100 closest documents.
# 3. Finally, the top 100 search results with its LLM descriptions, the search duration and the refined query will be returned.
# Note, that in this step we only return result IDs with its LLM description. In search_results_to_docs() we will query Solr to retrieve the document source code, etc. for each result ID.
def search(
    search_query,
    collection,
    prompts,
    model,
    config,
    document_index,
    refine_query=True,
    llm_output_cache=None,
):
    start = time.time()
    cached_duration = None
    docs_to_retrieve = 100
    refined_query = None

    if refine_query:
        # Load the prompt that will be used as an instruction to the LLM to refine the search query
        llm_prompt = prompts["search_refine"].format(search_query=search_query)

        # The cache is keyed by the model of the configured LLM backend, so switching backends or models
        # does not reuse responses that were generated by a different model.
        model_key = query_model_name(config)

        # Check if a cached response for the search query and prompt already exists
        if (
            llm_output_cache is not None
            and model_key in llm_output_cache
            and llm_prompt in llm_output_cache[model_key]
        ):
            print(f"Using cached LLM response for prompt '{llm_prompt[:200]}...'")
            refined_query = llm_output_cache[model_key][llm_prompt]["output"]
            # If using a cached response, also use a cached duration (i.e. the original response generation duration).
            # Otherwise the duration would be very short for consecutive benchmark runs and would falsify the benchmark result.
            cached_duration = llm_output_cache[model_key][llm_prompt]["output_duration"]
        else:
            # If config["enable_llm_output_cache"] is False, the method parameter llm_output_cache will be None. In that case reset it to an empty dictionary {} so we can write into it.
            llm_output_cache = llm_output_cache if llm_output_cache is not None else {}
            refined_query = model.generate(llm_prompt)

            end = time.time()
            output_duration = end - start

            if model_key not in llm_output_cache:
                llm_output_cache[model_key] = {}

            llm_output_cache[model_key][llm_prompt] = {
                "output": refined_query,
                "output_duration": output_duration,
            }

            if config["enable_llm_output_cache"]:
                save_llm_output_cache(llm_output_cache, config)

        try:
            refined_query = refined_query.split("<BEGIN>")[1]
            refined_query = refined_query.split("<END>")[0]
        except Exception:
            print(
                "Warning: Could not extract refined query using <BEGIN> and <END> from text generated by LLM for query '"
                + search_query
                + "', thus using it for search as is."
            )

        if config["add_user_query"]:
            search_query = search_query + "\n\n" + refined_query
        else:
            search_query = refined_query

        query_text = prompts["retrieve"].format(search_query=search_query)
    else:
        query_text = prompts["retrieve"].format(search_query=search_query)

    # Query the ChromaDB collection with the given query_text
    query_result = collection.query(
        query_texts=[query_text], n_results=docs_to_retrieve
    )
    results = {}

    # For each document retrieved, also add its LLM description and its ID
    for metadata, distance in zip(
        query_result["metadatas"][0], query_result["distances"][0]
    ):
        result_id = metadata["source"]
        results[result_id] = {
            "distance": distance,
            "id": result_id,
            "llm_description": document_index[result_id]["llm_description"],
        }

    end = time.time()
    search_duration = end - start

    if cached_duration is not None:
        search_duration = search_duration + cached_duration

    return {
        "results": results,
        "duration": search_duration,
        "refined_query": refined_query,
    }


# Given a list of search results with IDs, retrieve the documents from Solr.
# Additionaly this method adds a link to the original .thy-file in the repository at configured config["afp_remote_thys_folder_url"]
def search_results_to_docs(search_results, solr, config):
    ids = [_id for _id in search_results["results"]]

    for doc in docs_by_ids(solr, ids):
        doc_id = doc["id"]
        # Merge search_results with Solr documents
        search_results["results"][doc_id] = {**search_results["results"][doc_id], **doc}

        # Set default URLs to '#' which indicates the URL is not available
        search_results["results"][doc_id]["remote_url"] = "#"
        search_results["results"][doc_id]["entry_url"] = "#"
        search_results["results"][doc_id]["theory_url"] = "#"

        # Add direct link to the file in the remote repository and the entry URL
        # If the "ID" key starts with "USER_HOME", it's an entry from the AFP.
        # Otherwise, if it starts with "ISABELLE_HOME", it's a built-in theory file.
        # Then we can only add the link to the remote theory file (e.g. hosted on https://isabelle.in.tum.de/library/)
        if search_results["results"][doc_id]["id"].startswith("USER_HOME"):
            sub_path = search_results["results"][doc_id]["file"].split("/thys/")
            # If the file path does not contain /thys/ it means that the file does not exist in the repository
            if len(sub_path) > 1:
                # Add the line where the theorem code starts using #L... so that GitLab automatically jumps to the desired line when opening it in the browser
                search_results["results"][doc_id]["remote_url"] = (
                    config["afp_remote_thys_folder_url"]
                    + "/"
                    + sub_path[1]
                    + "#L"
                    + str(search_results["results"][doc_id]["start_line"])
                )

            # Extract the sub path for isa-afp.org
            sub_path = search_results["results"][doc_id]["url_path"].split("/")
            if len(sub_path) > 1:
                # We need the second last element from the URL path separated by /
                search_results["results"][doc_id]["entry_url"] = (
                    config["afp_remote_entry_url"] + "/" + sub_path[-2] + ".html"
                )
        else:
            # If it's a built-in theory file, we cannot add a remote or entry link, but we can add the link to the theory file (e.g. hosted on https://isabelle.in.tum.de/library/)
            sub_path = search_results["results"][doc_id]["url_path"]
            search_results["results"][doc_id]["theory_url"] = (
                config["isabelle_remote_theory_url"] + "/" + sub_path
            )

        # Remove HTML and XML from API response to lower response size and network usage
        del search_results["results"][doc_id]["html"]
        del search_results["results"][doc_id]["xml"]

    # Convert search_results["results"] to a list => this makes sorting or receiving the nth result easier
    search_results["results"] = [
        value for _, value in search_results["results"].items()
    ]
    return search_results
