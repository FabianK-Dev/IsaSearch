"""
bootstrap.py: This file contains the start-up sequence that is shared by every entry point of this
project (src/corpus.py, src/app.py, src/duplicates.py and benchmark/benchmark.py), so that the order
in which the components are initialized only has to be maintained in a single place.

- Solr: connects to a running Solr database reachable at config["solr_core_url"]
- Prompts: loads all prompts from prompts/ that will be fed to the embedding function and the LLM
- document_index: Builds the document_index, i.e. loads all documents (i.e. any theorem, lemma, corollary or proposition) from Solr and filters only necessary information (e.g. theorem source code, file name, session, etc.)
- document_descriptions: Loads or generates an informal description for each document using the configured LLM backend to allow more effective search with informal user queries
- ChromaDB: loads an embedding function from the configured pre-trained sentence transformer, creates a new or loads an existing ChromaDB collection and embeds any document that isn't already embedded
- LLM: Loads the configured LLM to refine user queries
- LLM cache: Loads an existing LLM output cache or creates a new one, if enabled.

The 'definitions' parameter adds a second corpus for definitional commands (definition, fun,
datatype, ...). It uses its own document index cache, its own descriptions artifact and its own
ChromaDB collection, so the theorem corpus stays untouched. It is either built (DEFINITIONS_BUILD,
used by the corpus build) or only attached to (DEFINITIONS_LOAD, used by the web application and the
duplicate detection, neither of which may start the multi hour informalization run).

The 'serve' parameter splits every entry point into two modes, which is what allows a deployed
server to run the web application and the duplicate detection at the same time:

- Build (serve=False): the one process that may write. It updates the AFP, builds the FindFacts
  index, fetches the document indexes, informalizes what is missing and embeds and prunes the
  ChromaDB collections. This is src/corpus.py, and it runs alone.
- Serve (serve=True): any number of processes that only read. Every one of those steps is turned
  off, and a corpus that was not built beforehand is reported instead of being built. This is the
  web application and the duplicate detection.

Every artifact therefore has exactly one writer, so no two processes can ever write the same file.
The one file a serving process still writes is its own LLM output cache (config["cache_folder"] plus
the cache name passed as 'llm_cache_name'), which is why the web application and the duplicate
detection use different names for it, and why only a single web application process may run.
"""

import json
import os

from src.solr import connect_solr, count_docs
from src.documents import (
    build_document_index,
    descriptions_artifact_path,
    document_index_cache_path,
    get_document_descriptions,
    relevant_definition_doc_keys,
    BUILD_CORPUS_COMMAND,
)
from src.embeddings import get_chromadb_collection, ensure_embedding_backend
from src.llm import (
    load_prompts,
    get_llm,
    get_llm_output_cache,
    ensure_llm_backend,
    DEFAULT_LLM_OUTPUT_CACHE,
)
from src.installation import (
    check_and_update,
    build_index,
    setup_isabelle_components,
    find_facts_home,
)


# Names of the artifacts that belong to the definitions corpus. They are deliberately different from
# the theorem ones ("document_index.json", "document_descriptions.json", "afp_docs"), so that the
# shipped theorem artifacts are never read or written by the duplicate detection.
DEFINITION_INDEX_CACHE = "definition_index.json"
DEFINITION_DESCRIPTIONS = "definition_descriptions.json"
DEFINITION_COLLECTION = "afp_definitions"
DEFINITION_DESCRIBE_PROMPT = "describe_definition"

# How boot_components treats the definitions corpus.
# - DEFINITIONS_BUILD fetches, informalizes and embeds whatever is missing. Only the corpus build
#   uses this, because informalizing all definitions takes hours.
# - DEFINITIONS_LOAD attaches to an already built corpus and never generates anything. If the corpus
#   does not exist, both the index and the collection are None and the caller has to cope with it.
DEFINITIONS_BUILD = "build"
DEFINITIONS_LOAD = "load"


# Documents without a description were never embedded and can therefore not be searched. A corpus
# that is only attached to is served without them instead of failing, because a partially built
# corpus is still useful. Documents whose description is outdated are kept: their embedding was built
# from that same outdated description, so they are still found consistently.
def described_documents(document_index, kind):
    described = {
        doc_id: doc
        for doc_id, doc in document_index.items()
        if "llm_description" in doc
    }

    if len(described) < len(document_index):
        print(
            f"Warning: {len(document_index) - len(described)} {kind} have no description and are "
            "therefore not searchable."
        )

    return described


# Load the configuration file, which is the only source of configuration in this project.
def load_config(config_path="config.json"):
    print("Loading config...")

    with open(config_path, "r") as file:
        data = file.read()
        return json.loads(data)


# Install or update the configured components and build the FindFacts index from them. This is
# everything a build does *before* Solr is contacted, and it is the only part that needs Solr to be
# stopped: 'isabelle find_facts_index' writes the same Lucene index that a serving Solr holds open,
# and the two cannot have it at the same time. It is therefore also runnable on its own, so that a
# deployment can index with Solr down and then start Solr for the rest of the build
# ('python3 -m src.corpus --index-only'). Running it twice is cheap: an index whose session list is
# unchanged is skipped.
def prepare_corpus_sources(config, check_updates=True, build_find_facts=True):
    if check_updates:
        print("Checking, downloading or updating the components if required...")
        if config.get("check_for_updates", True):
            components = config.get("components", {})

            for key, comp_config in components.items():
                check_and_update(key, comp_config)

    if build_find_facts:
        print("Setting up Isabelle components if required...")
        setup_isabelle_components(config)

        print("Building Isabelle FindFacts index if required...")
        build_index(config)


# Build the definitions corpus, i.e. the document index, the LLM descriptions and the ChromaDB
# collection for all documents matching config["solr_query_definitions"].
def build_definition_corpus(config, solr, prompts):
    solr_query = config["solr_query_definitions"]

    print("Counting definitions in Solr...")
    definition_count = count_docs(solr, solr_query)
    print(f"Solr contains {definition_count} definition blocks.")

    if definition_count == 0:
        # The theorem count tells the two possible causes apart, which matters because they have
        # opposite remedies. If the index holds theorems, then it and the 'command' field are fine
        # and the configured sessions simply contain no definitional commands - several small AFP
        # entries are nothing but lemmas. Only an index with nothing in it at all points at the
        # other cause, an Isabelle too old to index those commands.
        theorem_count = count_docs(solr, config["solr_query"])
        state_file = find_facts_home(config) / "indexed_sessions.json"

        if theorem_count > 0:
            raise RuntimeError(
                f"Solr returned {theorem_count} theorem blocks but no definitional ones, so the "
                f"index is fine and the sessions in config['isabelle_sessions'] "
                f"({config.get('isabelle_sessions')}) contain no definitions, functions, datatypes "
                f"or the like. Add sessions that do. Which commands were indexed can be listed "
                f"with a facet query:\n"
                f"  curl -s '{config['solr_core_url']}/select?q=*:*&rows=0&facet=true"
                f"&facet.field=command'"
            )

        raise RuntimeError(
            f"Solr returned no documents at all for query '{solr_query}'. If the FindFacts index "
            f"was built with an older Isabelle version that did not index definitional commands, "
            f"rebuild it by removing '{state_file}' and running "
            f"'python3 -m src.corpus --index-only' again."
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
    index_cache = document_index_cache_path(config, DEFINITION_INDEX_CACHE)
    descriptions = descriptions_artifact_path(config, DEFINITION_DESCRIPTIONS)

    for path in [index_cache, descriptions]:
        if not os.path.isfile(path):
            print(
                f"Definition search is disabled, because '{path}' does not exist. Build the "
                f"definitions corpus with '{BUILD_CORPUS_COMMAND}' first."
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
            artifact_name=DEFINITION_DESCRIPTIONS,
            describe_prompt_key=DEFINITION_DESCRIBE_PROMPT,
            generate_missing=False,
        )
    # ValueError also covers json.JSONDecodeError and UnicodeDecodeError, i.e. a file that is
    # truncated as well as one that is corrupted.
    except (ValueError, OSError) as error:
        print(
            f"Definition search is disabled, because the definitions corpus could not be read: "
            f"{error}. Rebuild it with '{BUILD_CORPUS_COMMAND}'."
        )
        return None, None

    described_index = described_documents(definition_index, "definitions")

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
            f"'{BUILD_CORPUS_COMMAND}' first."
        )
        return None, None

    return described_index, definition_collection


# Run the start-up sequence and return every component that the entry points need.
#
# - serve: run strictly read-only, see below
# - check_updates: clone or update the configured components (Isabelle and the AFP)
# - build_find_facts: set up the Isabelle components and build the FindFacts index if required
# - theorems: build or attach the theorem corpus. Disabling it saves loading a corpus an entry point
#   never touches, which is a considerable amount of memory for the AFP.
# - definitions: None, DEFINITIONS_BUILD or DEFINITIONS_LOAD, see the constants above
# - llm_cache_name: the LLM output cache this process owns, see DEFAULT_LLM_OUTPUT_CACHE. None means
#   it owns none and no cache is loaded, which is what the corpus build passes: it informalizes
#   through the artifacts and never queries the query LLM, so claiming a cache file that a serving
#   process rewrites as a whole would only put a second writer on it.
#
# 'serve' is what makes it safe to run several processes (the web application and the duplicate
# detection) next to each other on one machine: it turns off every path that writes. Nothing is
# cloned or indexed, no document index is fetched, no description is generated and nothing is
# embedded or pruned. Every artifact then has exactly one writer, namely the build run that has to
# happen before, and any number of readers.
def boot_components(
    config,
    serve=False,
    check_updates=True,
    build_find_facts=True,
    theorems=True,
    definitions=None,
    llm_cache_name=DEFAULT_LLM_OUTPUT_CACHE,
):
    if definitions not in [None, DEFINITIONS_BUILD, DEFINITIONS_LOAD]:
        raise ValueError(
            f"Unknown definitions mode '{definitions}', expected None, "
            f"'{DEFINITIONS_BUILD}' or '{DEFINITIONS_LOAD}'."
        )

    if serve and definitions == DEFINITIONS_BUILD:
        raise ValueError(
            "A serving process must not build the definitions corpus. Use "
            f"'{DEFINITIONS_LOAD}' or build it beforehand with "
            f"'{BUILD_CORPUS_COMMAND}'."
        )

    if serve:
        # These are not merely defaulted but overridden, so that a caller cannot end up writing from
        # a process that is supposed to only read.
        check_updates = False
        build_find_facts = False

    print("Checking LLM backend and preparing configured models if required...")
    ensure_llm_backend(config)

    print("Checking embedding backend...")
    ensure_embedding_backend(config)

    prepare_corpus_sources(
        config, check_updates=check_updates, build_find_facts=build_find_facts
    )

    print("Loading Solr...")
    solr = connect_solr(config)

    print("Loading prompts...")
    prompts = load_prompts(config)

    document_index = None
    collection = None

    if theorems:
        print("Building document index...")
        document_index = build_document_index(config, solr, read_only=serve)

        print("Getting document descriptions...")
        document_index = get_document_descriptions(
            config, document_index, prompts, generate_missing=not serve
        )

        if serve:
            document_index = described_documents(document_index, "theorems")

    definition_index = None
    definition_collection = None

    if definitions == DEFINITIONS_BUILD:
        definition_index, definition_collection = build_definition_corpus(
            config, solr, prompts
        )
    elif definitions == DEFINITIONS_LOAD:
        definition_index, definition_collection = load_definition_corpus(
            config, prompts
        )

    if theorems:
        print("Loading ChromaDB collection...")
        collection = get_chromadb_collection(
            config, prompts, document_index, add_missing=not serve
        )

        if serve and collection.count() == 0:
            raise RuntimeError(
                "The ChromaDB collection of the theorems is empty, thus nothing could be searched. "
                f"Build the corpus with '{BUILD_CORPUS_COMMAND}' first."
            )

    print("Loading LLM...")
    model = get_llm(config)

    llm_output_cache = None

    if llm_cache_name is not None:
        print("Loading LLM output cache if enabled via config...")
        llm_output_cache = get_llm_output_cache(config, llm_cache_name)

    return {
        "solr": solr,
        "prompts": prompts,
        "document_index": document_index,
        "collection": collection,
        "model": model,
        "llm_output_cache": llm_output_cache,
        "definition_index": definition_index,
        "definition_collection": definition_collection,
    }
