from src.solr import connect_solr
from src.documents import build_document_tree, get_document_descriptions
from src.embeddings import search, search_results_to_docs, get_chromadb_collection
from src.llm import load_prompts, get_llm, get_llm_output_cache
from benchmark.metrics import top_k_accuracy, normalized_discounted_cumulative_gain, reciprocal_rank, rank, calculate_mean_metrics, is_correct_target

from transformers import AutoTokenizer
from tqdm import tqdm
from pprint import pprint
from chromadb.utils import embedding_functions

import json
import pandas as pd
import torch

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

print("Loading Solr...")
solr = connect_solr(config)

if config["add_metadata"]:
    config["artifacts_folder"] = config["artifacts_folder"] + "-with-metadata"
    config["prompts_folder"] = config["prompts_folder"] + "-with-metadata"
    config["chroma_db_path"] = config["chroma_db_path"] + "-with-metadata"

print("Using config for benchmark:")
pprint(config)

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(config["vllm_name"])

print("Loading prompts...")
prompts = load_prompts(config)

print("Building document tree...")
document_tree = build_document_tree(config, solr)

print("Clearing CUDA cache...")
torch.cuda.empty_cache()

print("Getting document descriptions...")
document_tree = get_document_descriptions(config, document_tree, prompts, tokenizer)

print("Loading ChromaDB embedding function...")
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="sentence-transformers/multi-qa-distilbert-cos-v1", device='cuda')

print("Loading ChromaDB collection...")
collection = get_chromadb_collection(config, prompts, embedder, document_tree)

print("Loading LLM pipeline and gerneration arguments...")
model = get_llm(config, prompts, tokenizer)

print("Check if loading LLM output cache is enabled via config...")
llm_output_cache = get_llm_output_cache(config)

print("Loading benchmark CSV...")
benchmark_df = pd.read_csv('./benchmark/benchmark.csv')
benchmark_df = benchmark_df.reset_index()

query_columns = ['Title query', 'Natural language query']
benchmark_results = {}

for i, row in tqdm(benchmark_df.iterrows(), total=len(benchmark_df)):
    target_identifier = row["Target Identifier"]

    if not row["ID"] in benchmark_results:
        benchmark_results[row["ID"]] = {
            "metadata": {},
            "queries": {}
        }

    if row["Skip"] == True:
        print("Warning: Entry at row index " + str(i) + " and row ID '" + row["ID"] + "' is marked to be skipped with annotation: '" + str(row["Annotation"]) + "'")
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = "Annotation: " + str(row["Annotation"])
        continue

    if pd.isna(target_identifier):
        print("Warning: Target identifier JSON for row index " + str(i) + " and row ID '" + row["ID"] + "' does not exist. This benchmark entry will be skipped.")
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = "target_identifier_missing"
        continue

    try:
        target_identifier = json.loads(row["Target Identifier"])
    except:
        print("Warning: Target identifier JSON '" + row["Target Identifier"] + "' for row index " + str(i) + " and row ID '" + row["ID"] + "' could not be parsed. This benchmark entry will be skipped.")
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = "target_identifier_parse_error"
        continue

    target_exists = False
    print("Searching document identified by '" + row["Target Identifier"] + "'...")
    for doc_id in document_tree:
        if is_correct_target(document_tree[doc_id], target_identifier):
            target_exists = True
            break

    if not target_exists:
        print("Warning: No target document identified by '" + row["Target Identifier"] + "' exists in the document tree, thus skipping this entry.")
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = "target_document_not_found"
        continue

    for query_type in query_columns:
        query = row[query_type]

        if not pd.isna(query):
            # print(row)
            # print()
            print(f"Searching: \"{query}\"")

            results_dict = search(query, collection, prompts, model, config, llm_output_cache=llm_output_cache)
            results_list = search_results_to_docs(results_dict, document_tree)["results"]
            print(results_list[0])

            top_results = []
            for i, result in enumerate(results_list[:100]):
                score = result.get("score")
                doc_id = result.get("id")
                doc_src = result.get("src")
                doc_description = result.get("llm_description")
                doc_entity_kname = result.get("entity_kname")

                res = {
                    "rank": i + 1,
                    "score": score,
                    "id": doc_id,
                    "description": doc_description,
                    "entity_kname": doc_entity_kname,
                    "target_identifier": target_identifier,
                    "src": doc_src
                }

                top_results.append(res)

            benchmark_results[row["ID"]]["queries"][query_type] = {
                "metrics": {
                    "top_k_accuracy": top_k_accuracy(results_list, target_identifier),
                    "normalized_discounted_cumulative_gain": normalized_discounted_cumulative_gain(results_list, target_identifier),
                    "reciprocal_rank": reciprocal_rank(results_list, target_identifier),
                    "rank": rank(results_list, target_identifier),
                    "duration": results_dict["duration"]
                },
                "query": query,
                "refined_query": results_dict["refined_query"],
                "results[:10]": top_results,
                "duration": results_dict["duration"]
            }

benchmark_results["summary"] = calculate_mean_metrics(benchmark_results)

if config["add_metadata"]:
    benchmark_llm_name = config["vllm_name"].replace("/", "-") + "_" + config["llm_name"].replace("/", "-") + "_with_metadata"
else:
    benchmark_llm_name = config["vllm_name"].replace("/", "-") + "_" + config["llm_name"].replace("/", "-")

with open("./benchmark/benchmark_results_" + benchmark_llm_name + ".json", "w") as outfile:
    json.dump(benchmark_results, outfile, indent=4)
