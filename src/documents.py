import json
import os
import math
import re
import tomllib

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

def generate_document_descriptions(config):
    CACHE_FOLDER = config["cache_folder"]
    DOCUMENT_DESCRIPTIONS_CACHE = CACHE_FOLDER + "/" + config["document_descriptions"]

    # TODO: Verify if all documents are generated

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
