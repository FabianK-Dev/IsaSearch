from src.solr import connect_solr, docs_by_ids
from src.documents import build_document_tree
from src.embeddings import encode_embeddings, load_models, search, search_results_to_docs
from src.nltk_setup import init_nltk_corpora
from benchmark.metrics import top_k_accuracy, discounted_cumulative_gain, reciprocal_rank

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

query_columns = ['Title query', 'Natural language query']
benchmark_results = {}

for i, row in benchmark_df.iterrows():
    target_identifier = row["Target Identifier"]
    if pd.isna(target_identifier):
        continue

    try:
        target_identifier = json.loads(row["Target Identifier"])
    except:
        print("Warning: Target identifier JSON '" + row["Target Identifier"] + "' for row index " + str(i) + " and row ID '" + row["ID"] + "' could not be parsed. This benchmark entry will be skipped.")

    for query_type in query_columns:
        query = row[query_type]
        
        if not pd.isna(query):
            print(row)
            print()
            print(f"Searching: \"{query}\"")

            results_dict = search(query, encoded_embeddings, bi_encoder, cross_encoder, document_tree)
            results_list = search_results_to_docs(results_dict, solr)["results"]

            #top_k_accuracy(results_list, )

    # results = search("In an inner-product space, […] for any two orthogonal vectors v and w we have ‖v + w‖^2 = ‖v‖^2 + ‖w‖^2", encoded_embeddings, bi_encoder, cross_encoder, document_tree)

# for i, result in enumerate(search_results_to_docs(results, solr)["results"][:100]):
#     print("#" + str(i+1) + ": " + str(float(result["score"])) + ": " + result["id"])
