from vllm import LLM, SamplingParams
from vllm.distributed.parallel_state import destroy_model_parallel
from tqdm import tqdm

import gc
import torch
import json
import os
import math
import re
import tomllib
import zlib

def get_entry_metadata(entry, config):
    metadata_folder = config["afp_folder"] + "/metadata/"
    entry_toml = metadata_folder + "entries/" + entry + ".toml"

    if os.path.isfile(entry_toml):
        with open(entry_toml, "rb") as f:
            toml = tomllib.load(f)
            return toml
    else:
        print(f"No metadata file exists at path {entry_toml} for entry {entry}.")
        return {}

def relevant_doc_keys(solr_document):
    return {
        "id": solr_document["id"],
        "src": solr_document["src"],
        "entity_kname": solr_document.get("entity_kname", None)
    }

def fetch_all_docs(solr, config):
    document_tree = {}

    docs_per_page = 10000
    results = solr.search("command:theorem OR command:lemma OR command:corollary", start=0, rows=docs_per_page)
    max_docs = results.raw_response['response']['numFound']

    for result in results:
        result_filtered = relevant_doc_keys(result)
        document_tree[result["id"]] = result_filtered

    pages = math.ceil(max_docs / docs_per_page)
    for i in range(1, pages):
        print(f"Fetching page {i+1} of {pages} pages...")
        results = solr.search("command:theorem OR command:lemma OR command:corollary", start=i * docs_per_page, rows=docs_per_page)

        for result in results:
            result_filtered = relevant_doc_keys(result)
            document_tree[result["id"]] = result_filtered

    return document_tree

def generate_document_descriptions(config, document_tree, prompts, tokenizer, save_every=1000):
    ARTIFACTS_FOLDER = config["artifacts_folder"]
    DOCUMENT_DESCRIPTIONS = ARTIFACTS_FOLDER + "/" + "document_descriptions.json"

    if os.path.isfile(DOCUMENT_DESCRIPTIONS):
        print(f"Artifact {DOCUMENT_DESCRIPTIONS} already exists. Loading...")

        with open(DOCUMENT_DESCRIPTIONS, 'r') as file:
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
        checksum = zlib.adler32(doc["src"].encode('utf-8'))

        if doc["id"] not in document_descriptions:
            filtered_docs.append(doc)
        elif doc["id"] in document_descriptions:
            saved_checksum = document_descriptions[doc["id"]].get("zlib.adler32_checksum", "")
            if saved_checksum != checksum:
                print("Document identified by id '" + doc["id"] + "' already exists in document descriptions (" + saved_checksum + ") but doesn't match current zlib.adler32 checksum (" + checksum + "). This can happen if the theorem source code has changed. Adding to batch...")
                filtered_docs.append(doc)

    print("Found " + str(len(filtered_docs)) + " documents that need to be described by the LLM.")

    if len(filtered_docs) >= 1:
        print("Calculating maximum number of tokens required to describe filtered documents...")
        max_tokens = 0

        for doc in tqdm(filtered_docs):
            token_ids = tokenizer.encode(doc["src"].split("proof")[0].strip()[:config["theorem_max_length"]])
            num_tokens = len(token_ids)
            doc["num_tokens"] = num_tokens

            if num_tokens > max_tokens:
                max_tokens = num_tokens

        print(f"Max tokens in document tree (without prompt): {max_tokens}")
        
        describe_prompt_tokens = tokenizer.encode(prompts["describe"])
        max_tokens_prompt = max_tokens + len(describe_prompt_tokens)
        print("Max tokens for prompt and document string: " + str(max_tokens_prompt))

        doc_strings = []
        for doc in filtered_docs:
            doc_string = prompts["describe"].format(theorem_content=doc["src"].split("proof")[0].strip()[:config["theorem_max_length"]])
            doc_strings.append(doc_string)

        print("Loading LLM...")
        llm = LLM(
            model=config["llm_name"],
            max_model_len=max_tokens_prompt + config["llm_max_tokens"],
            dtype="auto",
            gpu_memory_utilization=config["gpu_memory_utilization"])
        sampling_params = SamplingParams(
            temperature=config["temperature"],
            top_p=config["top_p"],
            top_k=config["top_k"],
            max_tokens=config["llm_max_tokens"],
            stop=["<END>"])

        for i in tqdm(range(0, len(filtered_docs), save_every)):
            print("Document descriptions from index " + str(i) + " to " + str(i + save_every) + " of " + str(len(filtered_docs)) + " documents with maximum batch size " + str(save_every) + "...")
            outputs = llm.generate(doc_strings[i:i + save_every], sampling_params)

            for j, output in enumerate(outputs):
                doc_id = filtered_docs[i + j]["id"]
                doc_src = filtered_docs[i + j]["src"]
                raw_llm_description = output.outputs[0].text.strip()

                if j < 3:
                    print(f"Raw LLM output for doc_id {doc_id}: '{raw_llm_description}'")

                document_descriptions[doc_id] = {
                    "llm_description": raw_llm_description,
                    "zlib.adler32_checksum": zlib.adler32(doc_src.encode('utf-8')),
                    "model": config["llm_name"],
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
        torch.cuda.empty_cache()
        # torch.distributed.destroy_process_group()
        print("Finished deleting llm object and freeing GPU memory.")
    else:
        print("No documents need to be described by the LLM.")

    return document_descriptions

def get_document_descriptions(config, document_tree, prompts, tokenizer):
    document_descriptions = generate_document_descriptions(config, document_tree, prompts, tokenizer)

    print("Parsing LLM descriptions...")
    for doc_id in tqdm(document_descriptions):
        try:
            llm_description = document_descriptions[doc_id]["llm_description"].split("<BEGIN>")[1]
        except Exception as err:
            llm_description = document_descriptions[doc_id]["llm_description"]
            print(f"Warning: Could not extract theorem description using <BEGIN> and <END> from source provided by LLM for document with id \"{doc_id}\", thus loading it as is.")

        if doc_id in document_tree:
            document_tree[doc_id]["llm_description"] = llm_description
        else:
            print(f"Warning: LLM description for document with id {doc_id} does not exist in document tree and will thus be ignored.")

    return document_tree

def build_document_tree(config, solr):
    CACHE_FOLDER = config["cache_folder"]
    DOCUMENT_TREE_CACHE = f"{CACHE_FOLDER}/document_tree.json"

    if os.path.isfile(DOCUMENT_TREE_CACHE):
        print(f"Cached {DOCUMENT_TREE_CACHE} already exists. Loading...")

        with open(DOCUMENT_TREE_CACHE, 'r') as file:
            data = file.read()

        document_tree = json.loads(data)
        print(f"Finished loading {DOCUMENT_TREE_CACHE}")
    else:
        print(f"{DOCUMENT_TREE_CACHE} does not already exist. Fetching all documents...")
        document_tree = fetch_all_docs(solr, config)

        # Double check in case that the .cache folder already exists, but the entry_db_cache.json does not exist
        if not os.path.exists(CACHE_FOLDER):
            os.makedirs(CACHE_FOLDER)

        with open(DOCUMENT_TREE_CACHE, 'w') as file:
            json.dump(document_tree, file)

    return document_tree
