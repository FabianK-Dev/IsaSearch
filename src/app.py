from sentence_transformers import SentenceTransformer, CrossEncoder, util
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from benchmark import benchmark

import math
import json
import nltk
import os
import os.path
import re
import torch
import time
import pysolr

from solr import connect_solr
from documents import extract_docs, fetch_all_docs

print("Downloading stopwords corpus and check for updates...")
nltk.download('stopwords')

print("Downloading punkt_tab corpus for work tokenization and check for updates...")
nltk.download('punkt_tab')

print("Loading config...")

with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

AFP_FOLDER = config["afp_folder"]
CACHE_FOLDER = config["cache_folder"]
ENTRY_DB_CACHE = f"{CACHE_FOLDER}/entry_db_cache.json"

if os.path.isfile(ENTRY_DB_CACHE):
    print("Cached entry_db_cache.json already exists. Loading...")

    with open(ENTRY_DB_CACHE, 'r') as file:
        data = file.read()

    entry_db = json.loads(data)

    print(f"Finished loading {ENTRY_DB_CACHE}")
else:
    print(f"{ENTRY_DB_CACHE} does not already exist. Loading all entries...")

    fetch_all_docs(solr)
