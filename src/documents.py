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

def fetch_all_docs(solr):
    document_ids = []
    documents = []

    docs_per_page = 1000
    results = solr.search("command:theorem OR command:lemma OR command:corollary", start=0, rows=docs_per_page)
    max_docs = results.raw_response['response']['numFound']

    for result in results:
        extract_docs(result)
    
    pages = math.ceil(max_docs / docs_per_page)
    for i in range(pages):
        print(f"Fetching page {i+1} of {pages} pages...")
        results = solr.search("command:theorem OR command:lemma OR command:corollary", start=0, rows=docs_per_page)

        for result in results:
            doc_id, doc_str = extract_docs(result)
            document_ids.append(doc_id)
            documents.append(doc_str)

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
        print(f"{DOCUMENT_TREE_CACHE} does not already exist. Loading all entries...")

        fetch_all_docs(solr)

    return document_tree
