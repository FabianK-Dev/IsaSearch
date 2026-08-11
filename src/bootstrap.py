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

If 'include_definitions' is enabled, a second corpus is built for definitional commands
(definition, fun, datatype, ...). It uses its own document index cache, its own descriptions
artifact and its own ChromaDB collection, so the theorem corpus stays untouched.

Note: src/installation.py reads config.json independently at import time. That is left as-is here.
"""

import json

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


# Run the start-up sequence and return every component that the entry points need.
#
# - check_updates: clone or update the configured components (Isabelle and the AFP)
# - build_find_facts: set up the Isabelle components and build the FindFacts index if required
# - include_definitions: additionally build the definitions corpus (see build_definition_corpus)
# - keep_tokenizer: return the tokenizer instead of dropping it after the descriptions were generated
def boot_components(
    config,
    check_updates=True,
    build_find_facts=True,
    include_definitions=False,
    keep_tokenizer=False,
):
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

    if include_definitions:
        definition_index, definition_collection = build_definition_corpus(
            config, solr, prompts, tokenizer
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
