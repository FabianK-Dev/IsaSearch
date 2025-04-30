from src.solr import connect_solr, docs_by_ids
from src.documents import build_document_tree
from src.embeddings import encode_embeddings, load_models, search, search_results_to_docs
from src.nltk_setup import init_nltk_corpora

import json

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

init_nltk_corpora()
solr = connect_solr(config)
document_tree = build_document_tree(config, solr)
bi_encoder, cross_encoder = load_models(bi_encoder_model='flax-sentence-embeddings/st-codesearch-distilroberta-base', cross_encoder_model='nomic-ai/CodeRankEmbed')
encoded_embeddings = encode_embeddings(config, document_tree, bi_encoder)

results = search("Any consistent formal system F within which a certain amount of elementary arithmetic can be carried out is incomplete", encoded_embeddings, document_tree, bi_encoder, cross_encoder=None)
docs = search_results_to_docs(results, solr)["results"]

for doc in docs[:20]:
    print(str(float(doc["score"])) + ": " + doc["id"])
