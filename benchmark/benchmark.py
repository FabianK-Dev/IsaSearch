from src.solr import connect_solr, docs_by_ids
from src.documents import build_document_tree
from src.embeddings import encode_embeddings, load_encoders, search
from src.nltk_setup import init_nltk_corpora

import json

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

init_nltk_corpora()
solr = connect_solr(config)
document_tree = build_document_tree(config, solr)
encoded_embeddings = encode_embeddings(config, document_tree)
bi_encoder, cross_encoder = load_encoders()

results = search("Any consistent formal system F within which a certain amount of elementary arithmetic can be carried out is incomplete", encoded_embeddings, bi_encoder, cross_encoder, document_tree)
#results = search("Square Root of 2 is Irrational", encoded_embeddings, bi_encoder, cross_encoder, document_tree)
