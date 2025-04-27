from sentence_transformers import SentenceTransformer, CrossEncoder, util
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from benchmark import benchmark

from src.solr import connect_solr, docs_by_ids
from src.documents import build_document_tree
from src.embeddings import encode_embeddings, load_encoders, search

import math
import json
import nltk
import os
import os.path
import re
import time
import pysolr

print("Downloading stopwords corpus and checking for updates...")
nltk.download('stopwords')

print("Downloading punkt_tab corpus for work tokenization and checking for updates...")
nltk.download('punkt_tab')

print("Loading config...")

with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

solr = connect_solr(config)
document_tree = build_document_tree(config, solr)
encoded_embeddings = encode_embeddings(config, document_tree)
bi_encoder, cross_encoder = load_encoders()

results = search("\"sqrt(2) is not rational\" by assuming that it is rational and then deriving a falsehood", encoded_embeddings, bi_encoder, cross_encoder, document_tree)
#results = search("Square Root of 2 is Irrational", encoded_embeddings, bi_encoder, cross_encoder, document_tree)

id_list = [ r["id"] for r in results["results"] ]
print("IDs", id_list)
i = 0
for result in docs_by_ids(solr, id_list):
    i += 1
    if i > 10:
        break

    print(results["results"][0]["score"], result["id"], result["src"])
