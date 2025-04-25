from sentence_transformers import SentenceTransformer, CrossEncoder, util
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from benchmark import benchmark

import math
import json
import nltk
import os
import os.path
import torch
import time
import pysolr

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

AFP_FOLDER = config["afp_folder"]

print("Downloading stopwords corpus and check for updates...")
nltk.download('stopwords')

print("Downloading punkt_tab corpus for work tokenization and check for updates...")
nltk.download('punkt_tab')

CACHE_FOLDER = ".cache"
ENTRY_DB_CACHE = f"{CACHE_FOLDER}/entry_db_cache.json"
entry_db = {}

print(f"Connect to Solr at " + config["solr_core_url"] + "...")
solr = pysolr.Solr(config["solr_core_url"], always_commit=True, timeout=10)

print("Ping Solr for health check...")
solr.ping() # Health check

def extract_docs(doc):
    doc_str = doc["session"] + doc["src"] # TODO
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

if os.path.isfile(ENTRY_DB_CACHE):
    print("Cached entry_db_cache.json already exists. Loading...")

    with open(ENTRY_DB_CACHE, 'r') as file:
        data = file.read()

    entry_db = json.loads(data)

    print(f"Finished loading {ENTRY_DB_CACHE}")
else:
    print(f"{ENTRY_DB_CACHE} does not already exist. Loading all entries...")

    fetch_all_docs(solr)
