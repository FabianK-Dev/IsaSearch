from src.solr import connect_solr, docs_by_ids
from src.documents import build_document_tree
from src.embeddings import encode_embeddings, load_models, search, search_results_to_docs
from src.nltk_setup import init_nltk_corpora
from benchmark.metrics import top_k_accuracy, normalized_discounted_cumulative_gain, reciprocal_rank, calculate_mean_metrics

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

    if not row["ID"] in benchmark_results:
        benchmark_results[row["ID"]] = {}

    try:
        target_identifier = json.loads(row["Target Identifier"])
    except:
        print("Warning: Target identifier JSON '" + row["Target Identifier"] + "' for row index " + str(i) + " and row ID '" + row["ID"] + "' could not be parsed. This benchmark entry will be skipped.")
        benchmark_results[row["ID"]]["skipped"] = True
        continue

    for query_type in query_columns:
        query = row[query_type]
        
        if not pd.isna(query):
            print(row)
            print()
            print(f"Searching: \"{query}\"")

            results_dict = search(query, encoded_embeddings, bi_encoder, cross_encoder, document_tree)
            results_list = search_results_to_docs(results_dict, solr)["results"]

            benchmark_results[row["ID"]][query_type] = {
                "query": query,
                "top_k_accuracy": top_k_accuracy(results_list, target_identifier),
                "normalized_discounted_cumulative_gain": normalized_discounted_cumulative_gain(results_list, target_identifier),
                "reciprocal_rank": reciprocal_rank(results_list, target_identifier),
            }
    break

with open("./benchmark/benchmark_results.json", "w") as outfile:
    json.dump(benchmark_results, outfile, indent=4)

calculate_mean_metrics(benchmark_results)
