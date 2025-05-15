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

def extract_docs(doc, config):
    src_str = doc["src"]

    # Replace newlines through spaces
    src_str = re.compile(r"\n").sub(" ", src_str)

    # Replace two or more white spaces through single whitespace
    src_str = re.compile(r"\s+").sub(" ", src_str).strip()

    src_str = doc["theory"] + " " + src_str # Prepend the theory name
    return doc["id"], src_str

def fetch_all_docs(solr, config):
    document_ids = []
    documents = []

    docs_per_page = 10000
    results = solr.search("command:theorem OR command:lemma OR command:corollary", start=0, rows=docs_per_page)
    max_docs = results.raw_response['response']['numFound']

    for result in results:
        document_ids.append(result["id"])
        documents.append(result)

    pages = math.ceil(max_docs / docs_per_page)
    for i in range(1, pages):
        print(f"Fetching page {i+1} of {pages} pages...")
        results = solr.search("command:theorem OR command:lemma OR command:corollary", start=i * docs_per_page, rows=docs_per_page)

        for result in results:
            document_ids.append(result["id"])
            documents.append(result)

    document_tree = {
        "document_ids": document_ids,
        "documents": documents
    }

    return document_tree

def generate_document_descriptions(config, document_tree):
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

    for document in document_descriptions:
        document_data = next((doc for doc in document_tree["documents"] if doc["id"] == document), None)
        if document_data:
            checksum = zlib.adler32(document_data["src"].encode('utf-8'))
        else:
            print(f"Warning: Document with id {document} not found in document_tree.")
            continue
        document_descriptions[document] = {
            "llm_description": document_descriptions[document],
            "zlib.adler32_checksum": checksum
        }

    with open("./artifacts/document_descriptions.json", "w") as outfile:
        json.dump(document_descriptions, outfile, indent=4)

    # for document in document_tree["documents"]:
    #     checksum = zlib.adler32(document["src"].encode('utf-8'))

    #     if document["id"] not in document_descriptions:
    #         print("Document identified by id '" + document["id"] + "' does not already exist in document descriptions. Adding to batch...")
    #         filtered_docs.append(document)
    #     elif document["id"] in document_descriptions:
    #         saved_checksum = document_descriptions[document["id"]].get("zlib.adler32_checksum", "")
    #         if saved_checksum != checksum:
    #             print("Document identified by id '" + document["id"] + "' already exists in document descriptions (" + saved_checksum + ") but doesn't match current zlib.adler32 checksum (" + checksum + "). This can happen if the theorem source code has changed. Adding to batch...")

    exit()

def get_document_descriptions(config, document_tree):
    document_descriptions = generate_document_descriptions(config, document_tree)

    for doc_id in document_descriptions:
        try:
            llm_description = document_descriptions[doc_id].split("<BEGIN>")[1]
            llm_description = llm_description.split("<END>")[0]
        except Exception as err:
            llm_description = document_descriptions[doc_id]
            print(f"Warning: Could not extract theorem description using <BEGIN> and <END> from source provided by LLM for document with id \"{doc_id}\", thus loading it as is.")

        if doc_id in document_tree["document_ids"]:
            document_id_index = document_tree["document_ids"].index(doc_id)
            document_tree["documents"][document_id_index]["llm_description"] = llm_description
        else:
            print(f"Warning: LLM description for document with id {doc_id} does not exit in document tree and will thus be ignored.")

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

    max_characters, max_characters_id = 0, None
    total_characters = 0

    for i, document in enumerate(document_tree["documents"]):
        num_characters = len(document)
        total_characters += num_characters

        if num_characters > max_characters:
            max_characters = num_characters
            max_characters_id = document_tree["document_ids"][i]

    avg_chars_per_doc = total_characters / len(document_tree["documents"])
    avg_tokens_per_doc = avg_chars_per_doc / 4 # 1 token ~= 4 characters in English according to OpenAI (https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them)

    print(f"Average number of characters per document: {avg_chars_per_doc}")
    print(f"Average number of tokens per document: {avg_tokens_per_doc}")
    print(f"Largest theorem document: {max_characters_id}")

    return document_tree
