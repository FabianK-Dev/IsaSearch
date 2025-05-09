from src.solr import connect_solr
from src.documents import build_document_tree, get_document_descriptions
from src.embeddings import search, search_results_to_docs
from benchmark.metrics import top_k_accuracy, normalized_discounted_cumulative_gain, reciprocal_rank, rank, calculate_mean_metrics
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

import json
import pandas as pd
import chromadb

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

solr = connect_solr(config)
document_tree = build_document_tree(config, solr)
document_tree = get_document_descriptions(config, document_tree)

# Chroma setup
print("Creating ChromaDB storage and afp_docs collection...")
chroma_client = chromadb.PersistentClient(path="chroma_storage")
collection = chroma_client.get_or_create_collection("afp_docs")

print("Loading embedder...")
embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').to('cuda')
print("Finished loading embedder.")

instruction = "Represent the given natural language explanation concatenated with its formal math statement written in Isabelle/HOL for retrieving related statements by natural language query:"

# Get set of all already ecisting document IDs (saved at the source key)
existing = set()
for item in collection.get(include=["metadatas"])["metadatas"]:
    existing.add(item["source"])

for doc in tqdm(document_tree["documents"]):
    if doc["id"] in existing:
        continue

    doc_src =  doc["llm_description"].strip() + "\n\n" + doc["src"].strip()
    embedding = embedder.encode(instruction + "\n" + doc_src, convert_to_tensor=True).cpu().numpy()

    collection.add(
        documents=[doc_src],
        ids=[doc["id"]],
        metadatas=[{"source": doc["id"]}],
        embeddings=[embedding])

benchmark_df = pd.read_csv('./benchmark/benchmark.csv')
benchmark_df = benchmark_df.reset_index()  # make sure indexes pair with number of rows

query_columns = ['Title query', 'Natural language query']
benchmark_results = {}

for i, row in benchmark_df.iterrows():
    target_identifier = row["Target Identifier"]
    if pd.isna(target_identifier):
        continue

    if not row["ID"] in benchmark_results:
        benchmark_results[row["ID"]] = {
            "metadata": {},
            "queries": {}
        }

    try:
        target_identifier = json.loads(row["Target Identifier"])
    except:
        print("Warning: Target identifier JSON '" + row["Target Identifier"] + "' for row index " + str(i) + " and row ID '" + row["ID"] + "' could not be parsed. This benchmark entry will be skipped.")
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        continue

    for query_type in query_columns:
        query = row[query_type]
        
        if not pd.isna(query):
            print(row)
            print()
            print(f"Searching: \"{query}\"")

            results_dict = search(query, encoded_embeddings, bi_encoder, cross_encoder, document_tree)
            results_list = search_results_to_docs(results_dict, solr)["results"]

            print("Top 10 results:")
            for i, result in enumerate(results_list[:10]):
                score = result.get("score")
                doc_id = result["doc"].get("id")
                doc_src = result["doc"].get("src").split("proof")[0] if "proof" in result["doc"].get("src", "") else result["doc"].get("src")
                doc_entity_kname = result["doc"].get("entity_kname")
                print(f"{i + 1}. Score: {score}, ID: {doc_id}, KName: {doc_entity_kname} Src: {doc_src}")

            benchmark_results[row["ID"]]["queries"][query_type] = {
                "top_k_accuracy": top_k_accuracy(results_list, target_identifier),
                "normalized_discounted_cumulative_gain": normalized_discounted_cumulative_gain(results_list, target_identifier),
                "reciprocal_rank": reciprocal_rank(results_list, target_identifier),
                "rank": rank(results_list, target_identifier)
            }

benchmark_results["summary"] = calculate_mean_metrics(benchmark_results)

with open("./benchmark/benchmark_results.json", "w") as outfile:
    json.dump(benchmark_results, outfile, indent=4)
