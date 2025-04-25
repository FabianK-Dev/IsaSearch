import json
import os
import math
import re

def extract_docs(doc):
    doc_str = doc["src"]

    # Replace newlines through spaces
    doc_str = re.compile(r"\n").sub(" ", doc_str)

    # Replace two or more white spaces through single whitespace
    doc_str = re.compile(r"\s+").sub(" ", doc_str).strip()
    
    doc_str = doc["theory"] + " " + doc_str # Prepend the theory name
    return doc["id"], doc_str

# TODO
def get_entry_metadata(config, entry):
    metadata_folder = config["afp_folder"] + "/metadata/"
    entry_toml = metadata_folder + "/entries/" + entry + ".toml"

def fetch_all_docs(solr):
    document_ids = []
    documents = []

    docs_per_page = 1000
    results = solr.search("command:theorem OR command:lemma OR command:corollary", start=0, rows=docs_per_page)
    max_docs = results.raw_response['response']['numFound']

    for result in results:
        doc_id, doc_str = extract_docs(result)
        document_ids.append(doc_id)
        documents.append(doc_str)

    pages = math.ceil(max_docs / docs_per_page)
    for i in range(pages):
        print(f"Fetching page {i+1} of {pages} pages...")
        results = solr.search("command:theorem OR command:lemma OR command:corollary", start=0, rows=docs_per_page)

        for result in results:
            doc_id, doc_str = extract_docs(result)
            document_ids.append(doc_id)
            documents.append(doc_str)

    document_tree = {
        "document_ids": document_ids,
        "documents": documents
    }

    return document_tree

def build_document_tree(config, solr):
    CACHE_FOLDER = config["cache_folder"]
    DOCUMENT_TREE_CACHE = f"{CACHE_FOLDER}/document_tree.json"

    if os.path.isfile(DOCUMENT_TREE_CACHE):
        print("Cached {DOCUMENT_TREE_CACHE} already exists. Loading...")

        with open(DOCUMENT_TREE_CACHE, 'r') as file:
            data = file.read()

        document_tree = json.loads(data)
        print(f"Finished loading {DOCUMENT_TREE_CACHE}")
    else:
        print(f"{DOCUMENT_TREE_CACHE} does not already exist. Fetching all documents...")
        document_tree = fetch_all_docs(solr)

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
