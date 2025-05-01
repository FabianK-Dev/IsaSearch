from src.solr import connect_solr, docs_by_ids
from src.documents import build_document_tree
from src.embeddings import encode_embeddings, load_models, search, search_results_to_docs
from src.nltk_setup import init_nltk_corpora

import json
import pandas as pd

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

init_nltk_corpora()
solr = connect_solr(config)
document_tree = build_document_tree(config, solr)
bi_encoder, cross_encoder = load_models('flax-sentence-embeddings/st-codesearch-distilroberta-base', 'cross-encoder/ms-marco-MiniLM-L6-v2')
encoded_embeddings = encode_embeddings(config, document_tree, bi_encoder)

benchmark_df = pd.read_csv('./benchmark/benchmark.csv')
benchmark_df = benchmark_df.reset_index()  # make sure indexes pair with number of rows

for i, row in benchmark_df.iterrows():
    print(row['ID'], row['Natural language query'])

# results = search("Any consistent formal system F within which a certain amount of elementary arithmetic can be carried out is incomplete", encoded_embeddings, bi_encoder, cross_encoder, document_tree)
# results = search("In an inner-product space, […] for any two orthogonal vectors v and w we have ‖v + w‖^2 = ‖v‖^2 + ‖w‖^2", encoded_embeddings, bi_encoder, cross_encoder, document_tree)

# for i, result in enumerate(search_results_to_docs(results, solr)["results"][:100]):
#     print("#" + str(i+1) + ": " + str(float(result["score"])) + ": " + result["id"])
