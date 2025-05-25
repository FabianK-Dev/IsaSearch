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

# Qwen/Qwen2.5-3B-Instruct
benchmark_model = config["benchmark_llms"][1] # TODO: Iterate over all benchmark models instead of a fixed one
benchmark_subpath = benchmark_model.replace("/", "-")
print("Adjusting config for benchmark model '" + benchmark_model + "' and subpath '" + benchmark_subpath + "'...")

config["llm_name"] = benchmark_model
config["artifacts_folder"] = f"{config['artifacts_folder']}/{benchmark_subpath}"
config["chroma_db_path"] = f"{config['chroma_db_path']}/{benchmark_subpath}"
config["prompts_folder"] = f"{config['prompts_folder']}/{benchmark_subpath}"
# config["gpu_memory_utilization"] = 0.8
# config["sampling_parameters"]["temperature"] = 0.6
# config["sampling_parameters"]["top_p"] = 0.95
# config["sampling_parameters"]["min_p"] = 0
# config["sampling_parameters"]["top_k"] = 40
pprint(config)

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
if not os.path.exists(config["chroma_db_path"]):
    os.makedirs(config["chroma_db_path"])

chroma_client = chromadb.PersistentClient(path=config["chroma_db_path"] + "/chroma_db")
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
docs_to_embed = {
    "documents": [],
    "ids": [],
    "metadatas": [],
    "embeddings": []
}

print("Preparing documents before adding to collection...")
for doc_id in tqdm(filtered_tree):
    doc = document_tree[doc_id]
    doc_src = doc["llm_description"].strip() + "\n\n" + doc["src"].strip()
    embedding_str = prompts["embed"].format(doc_src=doc_src)
    embedding = embedder.encode(embedding_str, convert_to_tensor=True).cpu().numpy()

    docs_to_embed["documents"].append(doc_src)
    docs_to_embed["ids"].append(doc["id"])
    docs_to_embed["metadatas"].append({"source": doc["id"]})
    docs_to_embed["embeddings"].append(embedding)

if len(docs_to_embed["documents"]) > 0:
    collection.add(
        documents=docs_to_embed["documents"],
        ids=docs_to_embed["ids"],
        metadatas=docs_to_embed["metadatas"],
        embeddings=docs_to_embed["embeddings"])

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
    "max_new_tokens": config["sampling_parameters"]["max_tokens"],
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

for i, row in tqdm(benchmark_df.iterrows(), total=len(benchmark_df)):
    target_identifier = row["Target Identifier"]

    if not row["ID"] in benchmark_results:
        benchmark_results[row["ID"]] = {
            "metadata": {},
            "queries": {}
        }

    if row["Skip"] == "true":
        print("Warning: Entry at row index " + str(i) + " and row ID '" + row["ID"] + "' dis marked to be skipped with annotation: '" + row["Annotation"] + "'")
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = "Annotation: " + row["Annotation"]
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

            results_dict = search(query, collection, prompts, generation_args, pipe, config, llm_output_cache=llm_output_cache)
            results_list = search_results_to_docs(results_dict, document_tree)["results"]

            # print("Top 10 results:")
            # top_results = []
            # for i, result in enumerate(results_list[:10]):
            #     score = result.get("score")
            #     doc_id = result.get("id")
            #     doc_src = result.get("src")[:200] + "..."
            #     doc_description = result.get("llm_description")
            #     doc_entity_kname = result.get("entity_kname")

            #     res = {
            #         "rank": i + 1,
            #         "score": score,
            #         "id": doc_id,
            #         "description": doc_description,
            #         "entity_kname": doc_entity_kname,
            #         "src[:200]": doc_src
            #     }
                
            #     pprint(res)
            #     top_results.append(res)

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
                #"results[:10]": top_results,
                "duration": results_dict["duration"]
            }

benchmark_results["summary"] = calculate_mean_metrics(benchmark_results)

with open("./benchmark/benchmark_results.json", "w") as outfile:
    json.dump(benchmark_results, outfile, indent=4)
