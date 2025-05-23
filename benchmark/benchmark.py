from src.solr import connect_solr
from src.documents import build_document_tree, get_document_descriptions
from src.embeddings import search, search_results_to_docs
from src.llm import load_prompts
from benchmark.metrics import top_k_accuracy, normalized_discounted_cumulative_gain, reciprocal_rank, rank, calculate_mean_metrics, is_correct_target

from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from tqdm import tqdm
from pprint import pprint

import json
import pandas as pd
import chromadb
import os

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

print("Loading Solr...")
solr = connect_solr(config)

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(config["llm_name"])

print("Loading prompts...")
prompts = load_prompts(config)

print("Building document tree...")
document_tree = build_document_tree(config, solr)

# print("Clearing CUDA cache...")
# torch.cuda.empty_cache()

print("Getting document descriptions...")
document_tree = get_document_descriptions(config, document_tree, prompts, tokenizer)

# Chroma setup
print("Creating ChromaDB storage and afp_docs collection...")
chroma_client = chromadb.PersistentClient(path=config["chroma_db_path"])
collection = chroma_client.get_or_create_collection("afp_docs")

print("Loading embedder...")
embedder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2').to('cuda')
print("Finished loading embedder.")

# Get set of all already existing document IDs (saved at the source key)
existing = set()
metadata_response = collection.get(include=["metadatas"])

if "metadatas" in metadata_response and metadata_response["metadatas"] is not None:
    for item in metadata_response["metadatas"]:
        existing.add(item["source"])

filtered_tree = [doc_id for doc_id in document_tree if doc_id not in existing]

for doc_id in tqdm(filtered_tree):
    doc = document_tree[doc_id]
    if doc["id"] in existing:
        continue

    doc_src = doc["llm_description"].strip() + "\n\n" + doc["src"].strip()
    embedding_str = prompts["embed"].format(doc_src=doc_src)
    embedding = embedder.encode(embedding_str, convert_to_tensor=True).cpu().numpy()

    collection.add(
        documents=[doc_src],
        ids=[doc["id"]],
        metadatas=[{"source": doc["id"]}],
        embeddings=[embedding])

model = AutoModelForCausalLM.from_pretrained(
    config["llm_name"],
    device_map="auto",
    torch_dtype="auto")

tokenizer = AutoTokenizer.from_pretrained(config["llm_name"])

pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer)

generation_args = {
    "max_new_tokens": config["llm_max_tokens"],
    "return_full_text": False,
    "do_sample": False
}

benchmark_df = pd.read_csv('./benchmark/benchmark.csv')
benchmark_df = benchmark_df.reset_index()

query_columns = ['Title query', 'Natural language query']
benchmark_results = {}

llm_output_cache = None
if config["enable_llm_output_cache"]:
    CACHE_FOLDER = config["cache_folder"]
    LLM_OUTPUT_CACHE = f"{CACHE_FOLDER}/llm_output_cache.json"

    if not os.path.exists(LLM_OUTPUT_CACHE):
        print("Warning: LLM output cache file '" + LLM_OUTPUT_CACHE + "' does not exist, thus a new one will be created.")
        llm_output_cache = {}
    else:
        print("Loading LLM output cache...")
        with open(LLM_OUTPUT_CACHE, "r") as file:
            data = file.read()
            llm_output_cache = json.loads(data)
            print("Finished loading LLM output cache.")
else:
    print("LLM output caching is disabled in the config.")

for i, row in tqdm(benchmark_df.iterrows()):
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

    target_exists = False
    print("Searching document identified by '" + row["Target Identifier"] + "'...")
    for doc_id in document_tree:
        if is_correct_target(document_tree[doc_id], target_identifier):
            target_exists = True
            break

    if not target_exists:
        print("Warning: No target document identified by '" + row["Target Identifier"] + "' exists in the document tree, thus skipping this entry.")
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        continue

    for query_type in query_columns:
        query = row[query_type]

        if not pd.isna(query):
            print(row)
            print()
            print(f"Searching: \"{query}\"")

            results_dict = search(query, collection, prompts, generation_args, pipe, config, llm_output_cache=llm_output_cache)
            results_list = search_results_to_docs(results_dict, document_tree)["results"]

            print("Top 10 results:")
            top_results = []
            for i, result in enumerate(results_list[:10]):
                score = result.get("score")
                doc_id = result.get("id")
                doc_src = result.get("src")[:200] + "..."
                doc_description = result.get("llm_description")
                doc_entity_kname = result.get("entity_kname")

                res = {
                    "rank": i + 1,
                    "score": score,
                    "id": doc_id,
                    "description": doc_description,
                    "entity_kname": doc_entity_kname,
                    "src[:200]": doc_src
                }
                
                pprint(res)
                top_results.append(res)

            benchmark_results[row["ID"]]["queries"][query_type] = {
                "metrics": {
                    "top_k_accuracy": top_k_accuracy(results_list, target_identifier),
                    "normalized_discounted_cumulative_gain": normalized_discounted_cumulative_gain(results_list, target_identifier),
                    "reciprocal_rank": reciprocal_rank(results_list, target_identifier),
                    "rank": rank(results_list, target_identifier)
                },
                "query": query,
                "refined_query": results_dict["refined_query"],
                #"results[:10]": top_results,
                "duration": results_dict["duration"]
            }

benchmark_results["summary"] = calculate_mean_metrics(benchmark_results)

with open("./benchmark/benchmark_results.json", "w") as outfile:
    json.dump(benchmark_results, outfile, indent=4)
