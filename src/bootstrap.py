"""
bootstrap.py: This file contains the start-up sequence that is shared by every entry point of this
project (src/app.py, benchmark/benchmark.py and src/duplicates.py), so that the order in which the
components are initialized only has to be maintained in a single place.

- Solr: connects to a running Solr database reachable at config["solr_core_url"]
- Tokenizer: loads the configured tokenizer model to calculate the maximum number of tokens required for all prompts
- Prompts: loads all prompts from prompts/ that will be fed to the embedding function and the LLM
- document_index: Builds the document_index, i.e. loads all documents (i.e. any theorem, lemma, corollary or proposition) from Solr and filters only necessary information (e.g. theorem source code, file name, session, etc.)
- document_descriptions: Loads or generates an informal description for each document using the configured LLM backend to allow more effective search with informal user queries
- ChromaDB: loads an embedding function from the configured pre-trained sentence transformer, creates a new or loads an existing ChromaDB collection and embeds any document that isn't already embedded
- LLM: Loads the configured LLM to refine user queries
- LLM cache: Loads an existing LLM output cache or creates a new one, if enabled.

The 'definitions' parameter adds a second corpus for definitional commands (definition, fun,
datatype, ...). It uses its own document index cache, its own descriptions artifact and its own
ChromaDB collection, so the theorem corpus stays untouched. It is either built (DEFINITIONS_BUILD,
used by the duplicate detection) or only attached to (DEFINITIONS_LOAD, used by the web application,
which must never start the multi hour informalization run).

Note: src/installation.py reads config.json independently at import time. That is left as-is here.
"""

import json
import os

from transformers import AutoTokenizer

from src.solr import connect_solr, count_docs
from src.documents import (
    build_document_index,
    get_document_descriptions,
    relevant_definition_doc_keys,
)
from src.embeddings import get_chromadb_collection, ensure_embedding_backend
from src.llm import load_prompts, get_llm, get_llm_output_cache, ensure_llm_backend
from src.installation import (
    check_and_update,
    build_index,
    setup_isabelle_components,
    get_isabelle_version,
)


# Names of the artifacts that belong to the definitions corpus. They are deliberately different from
# the theorem ones ("document_index.json", "document_descriptions.json", "afp_docs"), so that the
# shipped theorem artifacts are never read or written by the duplicate detection.
DEFINITION_INDEX_CACHE = "definition_index.json"
DEFINITION_DESCRIPTIONS = "definition_descriptions.json"
DEFINITION_COLLECTION = "afp_definitions"
DEFINITION_DESCRIBE_PROMPT = "describe_definition"

# How boot_components treats the definitions corpus.
# - DEFINITIONS_BUILD fetches, informalizes and embeds whatever is missing. Only the duplicate
#   detection uses this, because informalizing all definitions takes hours.
# - DEFINITIONS_LOAD attaches to an already built corpus and never generates anything. If the corpus
#   does not exist, both the index and the collection are None and the caller has to cope with it.
DEFINITIONS_BUILD = "build"
DEFINITIONS_LOAD = "load"


# Load the configuration file, which is the only source of configuration in this project.
def load_config(config_path="config.json"):
    print("Loading config...")

    with open(config_path, "r") as file:
        data = file.read()
        return json.loads(data)


# Build the definitions corpus, i.e. the document index, the LLM descriptions and the ChromaDB
# collection for all documents matching config["solr_query_definitions"].
def build_definition_corpus(config, solr, prompts, tokenizer):
    solr_query = config["solr_query_definitions"]

    print("Counting definitions in Solr...")
    definition_count = count_docs(solr, solr_query)
    print(f"Solr contains {definition_count} definition blocks.")

    if definition_count == 0:
        raise RuntimeError(
            "Solr did not return any definitions for query '"
            + solr_query
            + "'. If the FindFacts index was built with an older Isabelle version that did not "
            "index definitional commands, rebuild it by removing "
            "~/.isabelle/find_facts/indexed_sessions.json and restarting the application."
        )

    print("Building definition index...")
    definition_index = build_document_index(
        config,
        solr,
        solr_query=solr_query,
        cache_name=DEFINITION_INDEX_CACHE,
        keys_fn=relevant_definition_doc_keys,
    )

    print("Getting definition descriptions...")
    definition_index = get_document_descriptions(
        config,
        definition_index,
        prompts,
        tokenizer,
        artifact_name=DEFINITION_DESCRIPTIONS,
        describe_prompt_key=DEFINITION_DESCRIBE_PROMPT,
    )

    print("Loading ChromaDB collection for definitions...")
    definition_collection = get_chromadb_collection(
        config, prompts, definition_index, collection_name=DEFINITION_COLLECTION
    )

    return definition_index, definition_collection


# Attach to an already built definitions corpus without generating or embedding anything.
# Returns (None, None) if the corpus does not exist or is empty, so that a caller can simply offer
# no definition search instead of failing.
#
# There are exactly three ways this could start expensive work, and all three are closed here: the
# document index is read from its cache file directly (so no Solr fetch can happen), the descriptions
# are attached with generate_missing disabled (so no LLM call can happen) and the collection is
# opened with add_missing disabled (so nothing can be embedded).
def load_definition_corpus(config, prompts):
    index_cache = f"{config['cache_folder']}/{DEFINITION_INDEX_CACHE}"
    descriptions = f"{config['artifacts_folder']}/{DEFINITION_DESCRIPTIONS}"

    for path in [index_cache, descriptions]:
        if not os.path.isfile(path):
            print(
                f"Definition search is disabled, because '{path}' does not exist. Build the "
                "definitions corpus with 'python3 -m src.duplicates --build-corpus-only' first."
            )
            return None, None

    # A build that was interrupted while writing one of these files leaves it truncated. That must
    # disable definition search instead of taking the whole application down with it, because the
    # theorem search does not depend on the definitions corpus at all.
    try:
        print(f"Loading definition index from {index_cache}...")
        with open(index_cache, "r") as file:
            definition_index = json.load(file)

        print("Getting definition descriptions...")
        definition_index = get_document_descriptions(
            config,
            definition_index,
            prompts,
            None,
            artifact_name=DEFINITION_DESCRIPTIONS,
            describe_prompt_key=DEFINITION_DESCRIBE_PROMPT,
            generate_missing=False,
        )
    # ValueError also covers json.JSONDecodeError and UnicodeDecodeError, i.e. a file that is
    # truncated as well as one that is corrupted.
    except (ValueError, OSError) as error:
        print(
            f"Definition search is disabled, because the definitions corpus could not be read: "
            f"{error}. Rebuild it with 'python3 -m src.duplicates --build-corpus-only'."
        )
        return None, None

    # Documents without a description were never embedded and therefore cannot be searched, so a
    # partially built corpus is served without them instead of failing. Documents whose description
    # is outdated are kept: their embedding was built from that same outdated description, so they
    # are still found consistently.
    described_index = {
        doc_id: doc
        for doc_id, doc in definition_index.items()
        if "llm_description" in doc
    }

    if len(described_index) < len(definition_index):
        print(
            f"Warning: {len(definition_index) - len(described_index)} definitions have no "
            "description and are therefore not searchable."
        )

    if len(described_index) == 0:
        print("Definition search is disabled, because no definition has a description.")
        return None, None

    print("Loading ChromaDB collection for definitions...")
    definition_collection = get_chromadb_collection(
        config,
        prompts,
        described_index,
        collection_name=DEFINITION_COLLECTION,
        add_missing=False,
    )

    if definition_collection.count() == 0:
        print(
            "Definition search is disabled, because the ChromaDB collection "
            f"'{DEFINITION_COLLECTION}' is empty. Build it with "
            "'python3 -m src.duplicates --build-corpus-only' first."
        )
        return None, None

    return described_index, definition_collection


# Run the start-up sequence and return every component that the entry points need.
#
# - check_updates: clone or update the configured components (Isabelle and the AFP)
# - build_find_facts: set up the Isabelle components and build the FindFacts index if required
# - definitions: None, DEFINITIONS_BUILD or DEFINITIONS_LOAD, see the constants above
# - keep_tokenizer: return the tokenizer instead of dropping it after the descriptions were generated
def boot_components(
    config,
    check_updates=True,
    build_find_facts=True,
    definitions=None,
    keep_tokenizer=False,
):
    if definitions not in [None, DEFINITIONS_BUILD, DEFINITIONS_LOAD]:
        raise ValueError(
            f"Unknown definitions mode '{definitions}', expected None, "
            f"'{DEFINITIONS_BUILD}' or '{DEFINITIONS_LOAD}'."
        )

    print("Checking LLM backend and preparing configured models if required...")
    ensure_llm_backend(config)

    print("Checking embedding backend...")
    ensure_embedding_backend(config)

    if check_updates:
        print("Checking, downloading or updating AFP if required...")
        if config.get("check_for_updates", True):
            components = config.get("components", {})

            for key, comp_config in components.items():
                check_and_update(key, comp_config)

    if build_find_facts:
        print("Setting up Isabelle components if required...")
        setup_isabelle_components()
        config["isabelle_version"] = get_isabelle_version()

        print("Building Isabelle FindFacts index if required...")
        build_index(config)

    print("Loading Solr...")
    solr = connect_solr(config)

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(config["tokenizer_name"])

    print("Loading prompts...")
    prompts = load_prompts(config)

    print("Building document index...")
    document_index = build_document_index(config, solr)

    print("Getting document descriptions...")
    document_index = get_document_descriptions(
        config, document_index, prompts, tokenizer
    )

    definition_index = None
    definition_collection = None

    if definitions == DEFINITIONS_BUILD:
        definition_index, definition_collection = build_definition_corpus(
            config, solr, prompts, tokenizer
        )
    elif definitions == DEFINITIONS_LOAD:
        definition_index, definition_collection = load_definition_corpus(
            config, prompts
        )

    if not keep_tokenizer:
        print("Deleting tokenizer object...")
        tokenizer = None
        print("Finished deleting tokenizer object.")

    print("Loading ChromaDB collection...")
    collection = get_chromadb_collection(config, prompts, document_index)

    print("Loading LLM...")
    model = get_llm(config)

    print("Loading LLM output cache if enabled via config...")
    llm_output_cache = get_llm_output_cache(config)

    return {
        "solr": solr,
        "tokenizer": tokenizer,
        "prompts": prompts,
        "document_index": document_index,
        "collection": collection,
        "model": model,
        "llm_output_cache": llm_output_cache,
        "definition_index": definition_index,
        "definition_collection": definition_collection,
    }
