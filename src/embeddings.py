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
import zlib
import chromadb
import requests

from tqdm import tqdm
from chromadb.api.types import EmbeddingFunction


from src.solr import docs_by_ids
from src.llm import (
    cached_output,
    extract_marked_output,
    query_model_name,
    save_llm_output_cache,
    store_output,
)
from src.openai_api import (
    openai_api_key,
    openai_headers,
    raise_for_status_with_body,
    status_error_message,
)

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

# Number of texts per request to the embedding server, overridable through
# config["openai_embedding_batch_size"].
DEFAULT_EMBEDDING_BATCH_SIZE = 32

# How long a single embedding request may take. Generous, because a server that is still loading its
# model can take a while to answer the first batch of a run.
EMBEDDING_REQUEST_TIMEOUT = 600

# Embedding models that are served through an OpenAI compatible API (e.g. Qwen3-Embedding) are
# trained for cosine similarity, whereas ChromaDB defaults to squared L2. This is a property of the
# embedder and not of the backend name, so it is carried by the embedding function itself.
COSINE_COLLECTION_METADATA = {"hnsw:space": "cosine"}


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
    # The distance function a collection built with this embedder has to use, read by
    # get_chromadb_collection. Embedders that are happy with ChromaDB's default do not define it.
    collection_metadata = COSINE_COLLECTION_METADATA

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
                    timeout=EMBEDDING_REQUEST_TIMEOUT,
                )

                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise RetryableEmbeddingError(
                        status_error_message(response, description)
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


# The name of the model that produces the embeddings, whichever backend is configured. Reports and
# benchmarks record this, so that a result can be traced back to the embedding space it was measured
# in. Reading config["chroma_db_embedder"] directly would name the local model even when everything
# is embedded remotely.
def embedding_model_name(config):
    if embedding_backend(config) == OPENAI_EMBEDDING_BACKEND:
        return config["openai_embedding_model"]

    return config["chroma_db_embedder"]


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
            config.get("openai_embedding_batch_size", DEFAULT_EMBEDDING_BATCH_SIZE),
            config.get(
                "openai_embedding_max_characters", DEFAULT_EMBEDDING_MAX_CHARACTERS
            ),
            openai_api_key(config),
        )

    # PyTorch and sentence-transformers are imported here and not at the top of the file, because
    # they are only needed by this backend. Importing PyTorch costs a few hundred megabytes of
    # resident memory, which is worth avoiding in every process that embeds through a remote server.
    import torch
    from chromadb.utils import embedding_functions

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


# Build the string that represents a document in the embedding space.
# Both the corpus side (get_chromadb_collection) and every query that is itself a document
# (see src/duplicates.py) must use this method, otherwise identical documents would not
# end up at the same place in the embedding space.
def document_embedding_string(doc, prompts):
    # Append an instruction before the document string, which improves the search quality in zero-shot situations.
    doc_src = doc["llm_description"].strip() + "\n\n" + doc["src"].strip()

    return prompts["embed"].format(doc_src=doc_src)


# The checksum of the source code a document was embedded from. It is stored next to every embedding,
# so that a later run can tell whether the text behind an embedding still is the current one. This is
# deliberately the same checksum that decides whether a document has to be informalized again (see
# generate_document_descriptions), because the embedded text is built from the description and the
# source code, and the description is regenerated exactly when the source code changes.
def source_checksum(doc):
    return zlib.adler32(doc["src"].encode("utf-8"))


# Refuse to delete more than this fraction of a collection in one run. Deleting a large part of the
# corpus is never a normal AFP update; it means that the document index is empty or belongs to a
# different corpus (e.g. a wrong config), and re-embedding everything afterwards would cost hours.
MAX_PRUNE_FRACTION = 0.5


# Bring the collection back in line with the document index by deleting everything that must not stay
# in it, and return the remaining {document id: checksum} entries so that the caller can embed what
# is missing afterwards.
#
# Two things are deleted:
# - documents that are no longer part of the corpus, i.e. theorems the AFP removed or moved. Nothing
#   ever removed them before, so they accumulated with every update and stayed searchable forever.
# - documents whose source code changed since they were embedded. Their description is regenerated
#   by the informalization step, but the embedding kept the text of the old version.
def reconcile_collection(collection, document_index, existing, collection_name):
    stale = [doc_id for doc_id in existing if doc_id not in document_index]

    outdated = [
        doc_id
        for doc_id, checksum in existing.items()
        if doc_id in document_index
        # A missing checksum means the document was embedded before checksums were stored, thus
        # whether it is outdated cannot be decided and it is left alone.
        and checksum is not None
        and checksum != source_checksum(document_index[doc_id])
    ]

    removable = stale + outdated

    if len(removable) == 0:
        print(
            f"ChromaDB collection '{collection_name}' is up to date, nothing to prune."
        )
        return existing

    # Only the documents that left the corpus are guarded against, because those are the ones that
    # are really lost. An outdated document is deleted and embedded again right afterwards, and a
    # corpus in which every source changed at once is a legitimate outcome of e.g. an Isabelle
    # release that reformats sources.
    if len(existing) > 0 and len(stale) > len(existing) * MAX_PRUNE_FRACTION:
        raise RuntimeError(
            f"Refusing to remove {len(stale)} of {len(existing)} documents from the ChromaDB "
            f"collection '{collection_name}'. Removing that much is not an AFP update, it means "
            "the document index does not belong to this collection. Check config['solr_query'], "
            "config['chroma_db_path'] and the document index cache. Delete the collection by hand "
            "if the corpus really did shrink that much."
        )

    print(
        f"Removing {len(stale)} documents that are no longer part of the corpus and "
        f"{len(outdated)} documents whose source code changed from ChromaDB collection "
        f"'{collection_name}'..."
    )

    # ChromaDB builds one statement per delete, so the ids are deleted in batches to keep a large
    # update from sending a single enormous request.
    for i in range(0, len(removable), 5000):
        collection.delete(ids=removable[i : i + 5000])

    removable_ids = set(removable)

    return {
        doc_id: checksum
        for doc_id, checksum in existing.items()
        if doc_id not in removable_ids
    }


# This method loads an existing or creates a new ChromaDB collection and embeds all documents that haven't been embedded, yet.
# 'collection_name' selects the collection inside the ChromaDB storage, so that different kinds of
# documents (e.g. theorems and definitions) can live in separate collections of the same storage.
# With 'add_missing' disabled the collection is only opened and nothing is embedded. The web
# application uses this to attach to an already built collection without doing any expensive work.
# With 'prune' enabled the collection is additionally brought in line with the document index, i.e.
# removed documents are deleted and changed documents are embedded again (see reconcile_collection).
# 'embedder' lets a caller that opens several collections share one embedding function between them
# (see boot_components): the local backend loads a model of a few hundred megabytes, so one per
# collection would multiply the memory of the process for identical copies.
def get_chromadb_collection(
    config,
    prompts,
    document_index,
    collection_name="afp_docs",
    add_missing=True,
    prune=True,
    embedder=None,
):
    if embedder is None:
        embedder = get_embedding_function(config)

    # ChromaDB path
    if not os.path.exists(config["chroma_db_path"]):
        os.makedirs(config["chroma_db_path"])

    # ChromaDB client and collection
    chroma_db_path = config["chroma_db_path"] + "/chroma_db"
    print("Loading ChromaDB collection at path '" + chroma_db_path + "'...")

    # The embedder decides which distance function its vectors need (see COSINE_COLLECTION_METADATA).
    # Collections that already exist keep their configured distance function, because ChromaDB
    # ignores the metadata of get_or_create_collection for them, thus existing collections stay
    # untouched.
    collection_metadata = getattr(embedder, "collection_metadata", None)

    chroma_client = chromadb.PersistentClient(path=chroma_db_path)
    collection = chroma_client.get_or_create_collection(
        collection_name, embedding_function=embedder, metadata=collection_metadata
    )

    if not add_missing:
        print(
            f"Attached to ChromaDB collection '{collection_name}' with "
            f"{collection.count()} documents without embedding anything."
        )
        return collection

    # Get all already existing document IDs (saved at the source key) with the checksum of the source
    # code they were embedded from. Collections that were built before checksums were stored have
    # None here, which is treated as "cannot tell" and never triggers a re-embedding, so upgrading
    # does not silently start a full re-embedding run.
    existing = {}
    metadata_response = collection.get(include=["metadatas"])

    if "metadatas" in metadata_response and metadata_response["metadatas"] is not None:
        for item in metadata_response["metadatas"]:
            existing[item["source"]] = item.get("checksum")

    print("Preparing documents before adding to ChromaDB collection...")

    if prune:
        # Deletes everything that is gone or outdated and returns what is left, so that the documents
        # whose source code changed are embedded again by the very same loop that embeds new ones.
        existing = reconcile_collection(
            collection, document_index, existing, collection_name
        )

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
            embedding_str = document_embedding_string(doc, prompts)

            doc_embeddings.append(embedding_str)
            metadatas.append({"source": doc["id"], "checksum": source_checksum(doc)})

        collection.add(documents=doc_embeddings, ids=doc_ids, metadatas=metadatas)

    return collection


# This search(...) method does the following:
# 1. If enabled, refine the search query using a LLM. If config["enable_llm_output_cache"] is enabled, it will use cached responses for cached search queries.
# 2. Combine the original search query and LLM-refined search query to search the ChromaDB collection for the top 100 closest documents.
# 3. Finally, the top 100 search results with its LLM descriptions, the search duration and the refined query will be returned.
# Note, that in this step we only return result IDs with its LLM description. In search_results_to_docs() we will query Solr to retrieve the document source code, etc. for each result ID.
# 'retrieve_prompt_key' and 'search_refine_prompt_key' select the prompts that are used. Their
# defaults are the prompts that were always used here, so callers that do not pass them (e.g. the
# benchmark) build exactly the same prompt strings and therefore also hit the same cache entries.
def search(
    search_query,
    collection,
    prompts,
    model,
    config,
    document_index,
    refine_query=True,
    llm_output_cache=None,
    retrieve_prompt_key="retrieve",
    search_refine_prompt_key="search_refine",
):
    start = time.time()
    cached_duration = None
    docs_to_retrieve = 100
    refined_query = None

    if refine_query:
        # Load the prompt that will be used as an instruction to the LLM to refine the search query
        llm_prompt = prompts[search_refine_prompt_key].format(search_query=search_query)

        # The cache is keyed by the model of the configured LLM backend, so switching backends or models
        # does not reuse responses that were generated by a different model.
        model_key = query_model_name(config)

        # Check if a cached response for the search query and prompt already exists
        cached = (
            cached_output(llm_output_cache, model_key, llm_prompt)
            if llm_output_cache is not None
            else None
        )

        if cached is not None:
            print(f"Using cached LLM response for prompt '{llm_prompt[:200]}...'")
            refined_query = cached["output"]
            # If using a cached response, also use a cached duration (i.e. the original response generation duration).
            # Otherwise the duration would be very short for consecutive benchmark runs and would falsify the benchmark result.
            cached_duration = cached["output_duration"]
        else:
            # If config["enable_llm_output_cache"] is False, the method parameter llm_output_cache will be None. In that case reset it to an empty dictionary {} so we can write into it.
            llm_output_cache = llm_output_cache if llm_output_cache is not None else {}
            refined_query = model.generate(llm_prompt)

            # Deliberately timed from the start of the whole search and not around the request
            # alone: this duration is replayed by cached benchmark runs, so its meaning must not
            # change between a cached and an uncached run.
            store_output(
                llm_output_cache,
                model_key,
                llm_prompt,
                refined_query,
                time.time() - start,
            )

            if config["enable_llm_output_cache"]:
                save_llm_output_cache(llm_output_cache, config)

        refined_query, extracted = extract_marked_output(refined_query)

        if not extracted:
            print(
                "Warning: Could not extract refined query using <BEGIN> and <END> from text generated by LLM for query '"
                + search_query
                + "', thus using it for search as is."
            )

        if config["add_user_query"]:
            search_query = search_query + "\n\n" + refined_query
        else:
            search_query = refined_query

    query_text = prompts[retrieve_prompt_key].format(search_query=search_query)

    # Query the ChromaDB collection with the given query_text
    query_result = collection.query(
        query_texts=[query_text], n_results=docs_to_retrieve
    )
    results = {}
    stale = 0

    # For each document retrieved, also add its LLM description and its ID
    for metadata, distance in zip(
        query_result["metadatas"][0], query_result["distances"][0]
    ):
        result_id = metadata["source"]

        # A collection is only ever added to, so it can still contain documents of an older version
        # of the document index. Those cannot be returned, because neither their description nor
        # their source code is available anymore.
        if result_id not in document_index:
            stale += 1
            continue

        results[result_id] = {
            "distance": distance,
            "id": result_id,
            "llm_description": document_index[result_id]["llm_description"],
        }

    if stale > 0:
        print(
            f"Warning: skipped {stale} results that are in the ChromaDB collection but not in the "
            "document index. The collection contains documents of an older version of the corpus."
        )

    end = time.time()
    search_duration = end - start

    if cached_duration is not None:
        search_duration = search_duration + cached_duration

    return {
        "results": results,
        "duration": search_duration,
        "refined_query": refined_query,
    }


# Add a link to the original .thy-file in the repository at configured config["afp_remote_thys_folder_url"],
# a link to the entry on isa-afp.org and a link to the theory file on isabelle.in.tum.de to the given document.
# The document is modified in place and requires the Solr keys "id", "file", "url_path" and "start_line".
def add_doc_urls(doc, config):
    # Set default URLs to '#' which indicates the URL is not available
    doc["remote_url"] = "#"
    doc["entry_url"] = "#"
    doc["theory_url"] = "#"

    # Add direct link to the file in the remote repository and the entry URL
    # If the "ID" key starts with "USER_HOME", it's an entry from the AFP.
    # Otherwise, if it starts with "ISABELLE_HOME", it's a built-in theory file.
    # Then we can only add the link to the remote theory file (e.g. hosted on https://isabelle.in.tum.de/library/)
    if doc["id"].startswith("USER_HOME"):
        sub_path = doc["file"].split("/thys/")
        # If the file path does not contain /thys/ it means that the file does not exist in the repository
        if len(sub_path) > 1:
            # Add the line where the theorem code starts using #L... so that GitLab automatically jumps to the desired line when opening it in the browser
            doc["remote_url"] = (
                config["afp_remote_thys_folder_url"]
                + "/"
                + sub_path[1]
                + "#L"
                + str(doc["start_line"])
            )

        # Extract the sub path for isa-afp.org
        sub_path = doc["url_path"].split("/")
        if len(sub_path) > 1:
            # We need the second last element from the URL path separated by /
            doc["entry_url"] = (
                config["afp_remote_entry_url"] + "/" + sub_path[-2] + ".html"
            )
    else:
        # If it's a built-in theory file, we cannot add a remote or entry link, but we can add the link to the theory file (e.g. hosted on https://isabelle.in.tum.de/library/)
        sub_path = doc["url_path"]
        doc["theory_url"] = config["isabelle_remote_theory_url"] + "/" + sub_path

    return doc


# Given a list of search results with IDs, retrieve the documents from Solr.
# Additionaly this method adds a link to the original .thy-file in the repository at configured config["afp_remote_thys_folder_url"]
def search_results_to_docs(search_results, solr, config):
    ids = [_id for _id in search_results["results"]]

    for doc in docs_by_ids(solr, ids):
        doc_id = doc["id"]
        # Merge search_results with Solr documents
        search_results["results"][doc_id] = {**search_results["results"][doc_id], **doc}

        add_doc_urls(search_results["results"][doc_id], config)

        # Remove HTML and XML from API response to lower response size and network usage
        del search_results["results"][doc_id]["html"]
        del search_results["results"][doc_id]["xml"]

    # Convert search_results["results"] to a list => this makes sorting or receiving the nth result easier
    search_results["results"] = [
        value for _, value in search_results["results"].items()
    ]
    return search_results
