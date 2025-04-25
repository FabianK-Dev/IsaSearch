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
from documents import build_document_tree

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
