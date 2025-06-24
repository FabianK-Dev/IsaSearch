from vllm import LLM, SamplingParams
from vllm.distributed.parallel_state import destroy_model_parallel
from tqdm import tqdm
from nltk.corpus import stopwords

import gc
import json
import os
import math
import tomllib
import zlib
import re
import nltk

cached_metadata = {}


def get_entry_metadata(entry, config):
    metadata_folder = config["afp_folder"] + "/metadata/"
    entry_toml = metadata_folder + "entries/" + entry + ".toml"

    if entry in cached_metadata:
        return cached_metadata[entry]

    if os.path.isfile(entry_toml):
        with open(entry_toml, "rb") as f:
            toml = tomllib.load(f)
            cached_metadata[entry] = {
                "title": toml.get("title", ""),
                "abstract": toml.get("abstract", ""),
            }
            return cached_metadata[entry]
    else:
        print(f"No metadata file exists at path {entry_toml} for entry {entry}.")
        cached_metadata[entry] = {"title": "", "abstract": ""}
        return cached_metadata[entry]


def relevant_doc_keys(solr_document, config):
    return {
        "id": solr_document["id"],
        "src": solr_document["src"],
        "entity_kname": solr_document.get("entity_kname", None),
        "metadata": get_entry_metadata(
            solr_document["session"], config
        ),  # Always load metadata to ensure cached document_tree.json always contains it, regardless of config["add_metadata"]
    }


# # TODO: remove in future
# benchmark_df = pd.read_csv('./benchmark/benchmark.csv')
# benchmark_df = benchmark_df.reset_index()
# target_identifiers = " ".join(benchmark_df["Target Identifier"].astype(str).tolist())

# # TODO: remove in future
# with open("benchmark/scrape_statistics.json", "r") as file:
#     data = file.read()
#     scrape_statistics = json.loads(data)


def fetch_all_docs(solr, config):
    document_tree = {}

    docs_per_page = 10000
    results = solr.search(
        "command:theorem OR command:lemma OR command:corollary",
        start=0,
        rows=docs_per_page,
    )
    max_docs = results.raw_response["response"]["numFound"]

    # TODO: remove in future
    # allow = 0
    for result in results:
        #     # TODO: remove in future
        #     if "entity_kname" in result and result["entity_kname"] in target_identifiers:
        #         result_filtered = relevant_doc_keys(result)
        #         document_tree[result["id"]] = result_filtered
        #         allow = 200
        #     elif allow > 0:
        #         allow -= 1
        result_filtered = relevant_doc_keys(result, config)
        document_tree[result["id"]] = result_filtered

    pages = math.ceil(max_docs / docs_per_page)
    for i in range(1, pages):
        print(f"Fetching page {i + 1} of {pages} pages...")
        results = solr.search(
            "command:theorem OR command:lemma OR command:corollary",
            start=i * docs_per_page,
            rows=docs_per_page,
        )

        # TODO: remove in future
        # allow = 0
        for result in results:
            #     # TODO: remove in future
            #     if "entity_kname" in result and result["entity_kname"] in target_identifiers:
            #         result_filtered = relevant_doc_keys(result)
            #         document_tree[result["id"]] = result_filtered
            #         allow = 200
            #     elif allow > 0:
            #         allow -= 1
            result_filtered = relevant_doc_keys(result, config)
            document_tree[result["id"]] = result_filtered

    return document_tree


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


def generate_document_descriptions(
    config, document_tree, prompts, tokenizer, save_every=1000
):
    ARTIFACTS_FOLDER = config["artifacts_folder"]
    DOCUMENT_DESCRIPTIONS = ARTIFACTS_FOLDER + "/" + "document_descriptions.json"

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
    for doc_id in tqdm(document_tree):
        doc = document_tree[doc_id]
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

    if len(filtered_docs) >= 1:
        # Only update NLTK resources if any documents need to be described and if adding metadata is enabled, to avoid unnecessary downloads
        print("Downloading/Updating NLTK resources (punkt and stopwords)...")
        nltk.download("punkt")
        nltk.download("stopwords")
        stop_words_set = set(stopwords.words("english"))

        doc_strings = []
        for doc in tqdm(filtered_docs):
            # Remove the proof part of the theorem source code, truncate to max length and strip trailing whitespaces
            theorem_content = (
                doc["src"].split("proof")[0][: config["theorem_max_length"]].strip()
            )

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

                doc_string = prompts["describe"].format(
                    theorem_content=theorem_content, title=title, abstract=abstract
                )
            else:
                doc_string = prompts["describe"].format(theorem_content=theorem_content)

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
        llm = LLM(
            model=config["vllm_name"],
            max_model_len=max_tokens + config["sampling_parameters"]["max_tokens"],
            dtype="auto",
            gpu_memory_utilization=config["gpu_memory_utilization"],
        )
        sampling_params = SamplingParams(
            temperature=config["sampling_parameters"]["temperature"],
            top_p=config["sampling_parameters"]["top_p"],
            top_k=config["sampling_parameters"]["top_k"],
            min_p=config["sampling_parameters"]["min_p"],
            max_tokens=config["sampling_parameters"]["max_tokens"],
            stop=config["sampling_parameters"]["stop"],
        )

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
            outputs = llm.generate(doc_strings[i : i + save_every], sampling_params)

            for j, output in enumerate(outputs):
                doc_id = filtered_docs[i + j]["id"]
                doc_src = filtered_docs[i + j]["src"]
                raw_llm_description = output.outputs[0].text.strip()

                if j < 3:
                    print(
                        f"Raw LLM output for doc_id {doc_id}: '{raw_llm_description}'"
                    )

                document_descriptions[doc_id] = {
                    "llm_description": raw_llm_description,
                    "zlib.adler32_checksum": zlib.adler32(doc_src.encode("utf-8")),
                    "model": config["vllm_name"],
                    "prompt": doc_strings[i + j],
                }

            print("Saving document descriptions to " + DOCUMENT_DESCRIPTIONS + "...")
            if not os.path.exists(ARTIFACTS_FOLDER):
                os.makedirs(ARTIFACTS_FOLDER)

            with open(DOCUMENT_DESCRIPTIONS, "w") as outfile:
                json.dump(document_descriptions, outfile, indent=4)

        print("Deleting llm object and freeing GPU memory...")
        destroy_model_parallel()
        del llm
        gc.collect()
        print("Finished deleting llm object and freeing GPU memory.")
    else:
        print("No documents need to be described by the LLM.")

    return document_descriptions


def get_document_descriptions(config, document_tree, prompts, tokenizer):
    document_descriptions = generate_document_descriptions(
        config, document_tree, prompts, tokenizer
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

        if doc_id in document_tree:
            document_tree[doc_id]["llm_description"] = llm_description

    if parsing_failed > 0:
        print(
            f"Warning: Could not extract theorem description using <BEGIN> and <END> from source provided by LLM for {parsing_failed} documents, thus loading them as-is."
        )

    return document_tree


def build_document_tree(config, solr):
    CACHE_FOLDER = config["cache_folder"]
    DOCUMENT_TREE_CACHE = f"{CACHE_FOLDER}/document_tree.json"

    if os.path.isfile(DOCUMENT_TREE_CACHE):
        print(f"Cached {DOCUMENT_TREE_CACHE} already exists. Loading...")

        with open(DOCUMENT_TREE_CACHE, "r") as file:
            data = file.read()

        document_tree = json.loads(data)
        print(f"Finished loading {DOCUMENT_TREE_CACHE}")
    else:
        print(
            f"{DOCUMENT_TREE_CACHE} does not already exist. Fetching all documents..."
        )
        document_tree = fetch_all_docs(solr, config)

        # Double check in case that the .cache folder already exists, but the entry_db_cache.json does not exist
        if not os.path.exists(CACHE_FOLDER):
            os.makedirs(CACHE_FOLDER)

        with open(DOCUMENT_TREE_CACHE, "w") as file:
            json.dump(document_tree, file)

    return document_tree
