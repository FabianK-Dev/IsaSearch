"""
documents.py: This file provides methods that can be used to generate natural language summaries for theorems using an LLM and cached metadata.
"""

import json
import os
import math
import tomllib
import zlib
import re
import nltk


from tqdm import tqdm
from nltk.corpus import stopwords

from src.llm import get_document_llm, document_model_name


cached_metadata = {}

# The 'proof' keyword as a whole word, i.e. not as part of an identifier such as 'proof_system'.
PROOF_KEYWORD = re.compile(r"(?<![A-Za-z0-9_'])proof(?![A-Za-z0-9_'])")


# Drop everything from the first 'proof' keyword on, so that only the statement remains.
# 'proof' has to be matched as a whole word here, because a lot of AFP entries name things like
# 'proofs' or 'soundness_proof_of'. Cutting inside such an identifier would leave an empty or
# meaningless statement, which would then be informalized and embedded as such.
def strip_proof(src):
    return PROOF_KEYWORD.split(src, maxsplit=1)[0]


# This method returns the metadata (i.e. title, abstract, authors, keywords, etc.) for a given entry
# from a local copy of the Archive of Formal Proofs (configured in config["afp_folder"]).
# Additionally this method caches loaded entires in the 'cached_metadata' dict.
def get_entry_metadata(entry, config):
    metadata_folder = config["components"]["afp"]["local_folder"] + "/metadata/"
    entry_toml = metadata_folder + "entries/" + entry + ".toml"

    if entry in cached_metadata:
        return cached_metadata[entry]

    if os.path.isfile(entry_toml):
        try:
            with open(entry_toml, "rb") as f:
                toml = tomllib.load(f)
                cached_metadata[entry] = {
                    "title": toml.get("title", ""),
                    "abstract": toml.get("abstract", ""),
                }
                return cached_metadata[entry]
        except Exception:
            print("Failed loading file " + entry_toml + ".")
            cached_metadata[entry] = {"title": "", "abstract": ""}
            return cached_metadata[entry]
    else:
        print(f"No metadata file exists at path {entry_toml} for entry {entry}.")
        cached_metadata[entry] = {"title": "", "abstract": ""}
        return cached_metadata[entry]


# This method only returns the ID, source code, entity_kname and the metadata for a given Solr document.
def relevant_doc_keys(solr_document, config):
    return {
        "id": solr_document["id"],
        "src": solr_document["src"],
        "entity_kname": solr_document.get("entity_kname", None),
        "metadata": get_entry_metadata(
            solr_document["session"], config
        ),  # Always load metadata to ensure cached document_index.json always contains it, regardless of config["add_metadata"]
    }


# Like relevant_doc_keys, but keeps the additional keys that the duplicate detection needs:
# - "command" tells which definitional command (definition, fun, datatype, ...) the block belongs to
# - "consts" and "typs" contain the constants and types that the block defines, which is used to
#   derive a syntactic ground truth in src/duplicates.py
# - "file", "url_path" and "start_line" allow building links without querying Solr again
def relevant_definition_doc_keys(solr_document, config):
    document = relevant_doc_keys(solr_document, config)

    document["command"] = solr_document.get("command", None)
    document["consts"] = solr_document.get("consts", []) or []
    document["typs"] = solr_document.get("typs", []) or []
    document["file"] = solr_document.get("file", None)
    document["url_path"] = solr_document.get("url_path", None)
    document["start_line"] = solr_document.get("start_line", None)

    return document


# This method fetches all documents, i.e. is any theorems, lemmas, corollaries and propositions
# from Solr in batches of 10000 documents per request.
# 'solr_query' defaults to config["solr_query"] and 'keys_fn' decides which Solr keys are kept,
# so that the same paging logic can also fetch definitions (see src/duplicates.py).
def fetch_all_docs(solr, config, solr_query=None, keys_fn=relevant_doc_keys):
    document_index = {}
    solr_query = solr_query if solr_query is not None else config["solr_query"]

    docs_per_page = 10000
    results = solr.search(
        solr_query,
        start=0,
        rows=docs_per_page,
    )
    # Because the first response contains the total number of documents, that we need to determine the amount of pages that will be loaded,
    # solr.search() has to be called once before the for loop, and then within the for loop for each following page.
    max_docs = results.raw_response["response"]["numFound"]

    for result in results:
        result_filtered = keys_fn(result, config)
        document_index[result["id"]] = result_filtered

    pages = math.ceil(max_docs / docs_per_page) if docs_per_page > 0 else 1
    for i in range(1, pages):
        print(f"Fetching page {i + 1} of {pages} pages...")
        results = solr.search(
            solr_query,
            start=i * docs_per_page,
            rows=docs_per_page,
        )

        for result in results:
            result_filtered = keys_fn(result, config)
            document_index[result["id"]] = result_filtered

    return document_index


# This method returns only relevant information from a given entry metadata (i.e. title, abstract, etc.).
# It removes newlines, short words, non-alphabetic characters, multiple or trailing whitespaces and stop words.
# This is done to decrease the amount of tokens required per informalized theorem.
def prepare_metadata(metadata, stop_words_set):
    # Replace newlines through spaces
    plain_text = metadata.lower().replace("\n", " ")

    # Replace 1-3 letter words and non-alphabetic characters with a single whitespace
    plain_text = re.sub(r"\b[a-z]{1,3}\b|[^a-z ]", " ", plain_text)

    # Replace two or more white spaces through single whitespace
    plain_text = re.sub(r"\s+", " ", plain_text).strip()

    # Remove stop words like e.g. "the", "a", "and", etc.
    plain_text_tokens = plain_text.split()
    tokens_without_stopwords = [
        word for word in plain_text_tokens if word not in stop_words_set
    ]

    plain_text = " ".join(tokens_without_stopwords)
    return plain_text


# This document generates document descriptions. That means that a LLM summaries each theorem into natural language.
# This process is only done for theorems that haven't been summarized or whose source code has changed.
# Source code changes are detected by calculating, saving and comparing the Adler32 checksum for a theorem's source code.
# Document summaries are generated by the configured LLM backend (Ollama or llama.cpp) through its local HTTP API.
# Generated document descriptions will be saved to the artifacts folder, configured at config["artifacts_folder"].
#
# 'artifact_name' and 'describe_prompt_key' allow describing another kind of document (e.g. definitions)
# into a separate artifact file with a separate prompt, without touching the theorem artifact.
def generate_document_descriptions(
    config,
    document_index,
    prompts,
    tokenizer,
    save_every=1000,
    artifact_name="document_descriptions.json",
    describe_prompt_key="describe",
    generate_missing=True,
):
    ARTIFACTS_FOLDER = config["artifacts_folder"]
    DOCUMENT_DESCRIPTIONS = ARTIFACTS_FOLDER + "/" + artifact_name

    # With generate_missing disabled no LLM is called at all, so the prompt does not have to exist
    # and no tokenizer is required. This is used by the web application, which must never start a
    # multi hour informalization run just because a description is missing.
    if generate_missing and describe_prompt_key not in prompts:
        raise KeyError(
            f"Prompt '{describe_prompt_key}' does not exist in the prompts folder "
            f"'{config['prompts_folder']}'. Expected a file named '{describe_prompt_key}.txt'."
        )

    if os.path.isfile(DOCUMENT_DESCRIPTIONS):
        print(f"Artifact {DOCUMENT_DESCRIPTIONS} already exists. Loading...")

        with open(DOCUMENT_DESCRIPTIONS, "r") as file:
            data = file.read()

        document_descriptions = json.loads(data)
        print(f"Finished loading {DOCUMENT_DESCRIPTIONS}")
    else:
        print(f"{DOCUMENT_DESCRIPTIONS} does not already exist.")
        document_descriptions = {}

    print("Finding documents that need to be described by the LLM...")

    filtered_docs = []
    # For each document in the document_index, calculate its Adler32 checksum, to determine whether it was changed.
    # All documents that need to be described by the LLM will be appended to filtered_docs.
    for doc_id in tqdm(document_index):
        doc = document_index[doc_id]
        checksum = zlib.adler32(doc["src"].encode("utf-8"))

        if doc["id"] not in document_descriptions:
            filtered_docs.append(doc)
        elif doc["id"] in document_descriptions:
            saved_checksum = document_descriptions[doc["id"]].get(
                "zlib.adler32_checksum", ""
            )
            if saved_checksum != checksum:
                print(
                    "Document identified by id '"
                    + doc["id"]
                    + "' already exists in document descriptions ("
                    + str(saved_checksum)
                    + ") but doesn't match current zlib.adler32 checksum ("
                    + str(checksum)
                    + "). This can happen if the theorem source code has changed. Adding to batch..."
                )
                filtered_docs.append(doc)

    print(
        "Found "
        + str(len(filtered_docs))
        + " documents that need to be described by the LLM."
    )

    if not generate_missing:
        # A document that was never described has no description to attach and is therefore dropped
        # by the caller. A document whose source code changed still has its old description, which is
        # also the text its embedding was built from, so it stays usable but is outdated.
        undescribed = [
            doc for doc in filtered_docs if doc["id"] not in document_descriptions
        ]
        outdated = len(filtered_docs) - len(undescribed)

        if len(undescribed) >= 1:
            print(
                f"Warning: {len(undescribed)} documents have no description at all and can "
                "therefore not be searched."
            )

        if outdated >= 1:
            print(
                f"Warning: {outdated} documents have a description of an older version of their "
                "source code and are searched with that outdated description."
            )

        if len(filtered_docs) >= 1:
            print(
                "Rebuild the corpus with 'python3 -m src.duplicates --build-corpus-only' to "
                "describe them."
            )

        return document_descriptions

    if len(filtered_docs) >= 1:
        # Only update NLTK resources if any documents need to be described, to avoid unnecessary downloads
        print("Downloading/Updating NLTK resources (punkt and stopwords)...")
        nltk.download("punkt")
        nltk.download("stopwords")
        stop_words_set = set(stopwords.words("english"))

        doc_strings = []
        # Create all doc_strings, i.e. all prompts that contain the theorems and metadata, if enabled, along with the instructions for the LLM
        for doc in tqdm(filtered_docs):
            # Remove the proof part of the theorem source code, truncate to max length and strip trailing whitespaces
            theorem_content = strip_proof(doc["src"])[
                : config["theorem_max_length"]
            ].strip()

            # If enabled, add the metadata to the prompt, otherwise only provive the theorem content.
            if config["add_metadata"]:
                title = prepare_metadata(
                    doc["metadata"].get("title", ""), stop_words_set
                )
                abstract = prepare_metadata(
                    doc["metadata"].get("abstract", ""), stop_words_set
                )

                if len(title + abstract) > config["metadata_max_length"]:
                    abstract = (
                        abstract[: config["metadata_max_length"] - len(title) - 3]
                        + "..."
                    )

                if title == "":
                    title = "-- no title --"
                if abstract == "":
                    abstract = "-- no abstract --"

                doc_string = prompts[describe_prompt_key].format(
                    theorem_content=theorem_content, title=title, abstract=abstract
                )
            else:
                doc_string = prompts[describe_prompt_key].format(
                    theorem_content=theorem_content
                )

            doc_strings.append(doc_string)

        print(
            "Calculating maximum number of tokens required to describe filtered documents..."
        )
        max_tokens = 0

        for doc in tqdm(doc_strings):
            token_ids = tokenizer.encode(doc)
            num_tokens = len(token_ids)

            if num_tokens > max_tokens:
                max_tokens = num_tokens

        print("Max tokens for prompt and document string: " + str(max_tokens))

        print("Loading LLM...")
        llm = get_document_llm(config)

        # Generate document descriptions for all filtered_docs
        for i in tqdm(range(0, len(filtered_docs), save_every)):
            print(
                "Document descriptions from index "
                + str(i)
                + " to "
                + str(i + save_every)
                + " of "
                + str(len(filtered_docs))
                + " documents with maximum batch size "
                + str(save_every)
                + "..."
            )
            batch_doc_strings = doc_strings[i : i + save_every]
            for j, doc_string in enumerate(tqdm(batch_doc_strings)):
                doc_id = filtered_docs[i + j]["id"]
                doc_src = filtered_docs[i + j]["src"]
                raw_llm_description = llm.generate(doc_string).strip()

                # For debugging purposes, only print the first the generated document descriptions
                if j < 3:
                    print(
                        f"Raw LLM output for doc_id {doc_id}: '{raw_llm_description}'"
                    )

                document_descriptions[doc_id] = {
                    "llm_description": raw_llm_description,
                    "zlib.adler32_checksum": zlib.adler32(doc_src.encode("utf-8")),
                    "model": document_model_name(config),
                    "prompt": doc_string,
                }

            print("Saving document descriptions to " + DOCUMENT_DESCRIPTIONS + "...")
            if not os.path.exists(ARTIFACTS_FOLDER):
                os.makedirs(ARTIFACTS_FOLDER)

            with open(DOCUMENT_DESCRIPTIONS, "w") as outfile:
                json.dump(document_descriptions, outfile, indent=4)

        print("Finished generating document descriptions.")
    else:
        print("No documents need to be described by the LLM.")

    return document_descriptions


# This method loads already generated document descriptions from the artifacts folder, configured at config["artifacts_folder"].
# It then extracts the content within the <BEGIN> and <END> parts. If extracting the content fails, we simply take the entire LLM output as is.
def get_document_descriptions(
    config,
    document_index,
    prompts,
    tokenizer,
    artifact_name="document_descriptions.json",
    describe_prompt_key="describe",
    generate_missing=True,
):
    document_descriptions = generate_document_descriptions(
        config,
        document_index,
        prompts,
        tokenizer,
        artifact_name=artifact_name,
        describe_prompt_key=describe_prompt_key,
        generate_missing=generate_missing,
    )

    print("Parsing LLM descriptions...")
    parsing_failed = 0

    for doc_id in tqdm(document_descriptions):
        try:
            llm_description = document_descriptions[doc_id]["llm_description"].split(
                "<BEGIN>"
            )[1]
        except Exception:
            parsing_failed += 1
            llm_description = document_descriptions[doc_id]["llm_description"]

        if doc_id in document_index:
            document_index[doc_id]["llm_description"] = llm_description

    if parsing_failed > 0:
        print(
            f"Warning: Could not extract theorem description using <BEGIN> and <END> from source provided by LLM for {parsing_failed} documents, thus loading them as-is."
        )

    return document_index


# Building the document index means, saving all loaded documents with its loaded entry metadata.
# This is done to avoid having to refetch all documents from Solr on every program start.
def build_document_index(
    config,
    solr,
    solr_query=None,
    cache_name="document_index.json",
    keys_fn=relevant_doc_keys,
):
    CACHE_FOLDER = config["cache_folder"]
    DOCUMENT_INDEX_CACHE = f"{CACHE_FOLDER}/{cache_name}"

    if os.path.isfile(DOCUMENT_INDEX_CACHE):
        print(f"Cached {DOCUMENT_INDEX_CACHE} already exists. Loading...")

        with open(DOCUMENT_INDEX_CACHE, "r") as file:
            data = file.read()

        document_index = json.loads(data)
        print(f"Finished loading {DOCUMENT_INDEX_CACHE}")
    else:
        print(
            f"{DOCUMENT_INDEX_CACHE} does not already exist. Fetching all documents..."
        )
        document_index = fetch_all_docs(
            solr, config, solr_query=solr_query, keys_fn=keys_fn
        )

        # Double check in case that the .cache folder already exists, but the entry_db_cache.json does not exist
        if not os.path.exists(CACHE_FOLDER):
            os.makedirs(CACHE_FOLDER)

        with open(DOCUMENT_INDEX_CACHE, "w") as file:
            json.dump(document_index, file)

    return document_index
