from src.solr import connect_solr
from src.documents import build_document_index, get_document_descriptions
from src.embeddings import search, search_results_to_docs, get_chromadb_collection
from src.llm import load_prompts, get_llm, get_llm_output_cache
from benchmark.metrics import (
    top_k_accuracy,
    normalized_discounted_cumulative_gain,
    reciprocal_rank,
    rank,
    calculate_mean_metrics,
    is_correct_target,
)

from transformers import AutoTokenizer
from tqdm import tqdm
from pprint import pprint
from nltk.corpus import stopwords

import json
import pandas as pd
import os
import nltk
import random
import re

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

print("Loading Solr...")
solr = connect_solr(config)

results_suffix = "_"
if config["add_metadata"]:
    results_suffix = results_suffix + "M"

if config["add_user_query"]:
    results_suffix = results_suffix + "U"

if config["benchmark_search_refine"]:
    results_suffix = results_suffix + "R"

if results_suffix == "_":
    results_suffix = "_baseline"

print("Using config for benchmark:")
pprint(config)

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(config["vllm_name"])

print("Loading prompts...")
prompts = load_prompts(config)

print("Building document index...")
document_index = build_document_index(config, solr)

print("Getting document descriptions...")
document_index = get_document_descriptions(config, document_index, prompts, tokenizer)

print("Clean up tokenizer to free up memory")
del tokenizer

print("Loading ChromaDB collection...")
collection = get_chromadb_collection(config, prompts, document_index)

print("Loading LLM pipeline and gerneration arguments...")
model = get_llm(config)

print("Check if loading LLM output cache is enabled via config...")
llm_output_cache = get_llm_output_cache(config)

print("Downloading/Updating NLTK resources (punkt and stopwords)...")
nltk.download("punkt")
nltk.download("stopwords")
stop_words_set = set(stopwords.words("english"))

print("Loading benchmark CSV...")
benchmark_df = pd.read_csv("./benchmark/benchmark.csv")
benchmark_df = benchmark_df.reset_index()

query_columns = [
    "Title query",
    "Natural language query",
    "Noisy natural language query",
]
benchmark_results = {}

for i, row in tqdm(benchmark_df.iterrows(), total=len(benchmark_df)):
    target_identifier = row["Target Identifier"]

    if row["ID"] not in benchmark_results:
        benchmark_results[row["ID"]] = {"metadata": {}, "queries": {}}

    if row["Skip"]:
        print(
            "Warning: Entry at row index "
            + str(i)
            + " and row ID '"
            + row["ID"]
            + "' is marked to be skipped with annotation: '"
            + str(row["Annotation"])
            + "'"
        )
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = (
            "Annotation: " + str(row["Annotation"])
        )
        continue

    if pd.isna(target_identifier):
        print(
            "Warning: Target identifier JSON for row index "
            + str(i)
            + " and row ID '"
            + row["ID"]
            + "' does not exist. This benchmark entry will be skipped."
        )
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = (
            "target_identifier_missing"
        )
        continue

    try:
        target_identifier = json.loads(row["Target Identifier"])
    except json.JSONDecodeError:
        print(
            "Warning: Target identifier JSON '"
            + row["Target Identifier"]
            + "' for row index "
            + str(i)
            + " and row ID '"
            + row["ID"]
            + "' could not be parsed. This benchmark entry will be skipped."
        )
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = (
            "target_identifier_parse_error"
        )
        continue

    # Remove duplicates from target_identifier (list of dicts)
    target_identifier = [dict(t) for t in {tuple(d.items()) for d in target_identifier}]

    target_exists = False
    print("Searching document identified by '" + row["Target Identifier"] + "'...")
    for doc_id in document_index:
        if is_correct_target(document_index[doc_id], target_identifier):
            target_exists = True
            break

    if not target_exists:
        print(
            "Warning: No target document identified by '"
            + row["Target Identifier"]
            + "' exists in the document index, thus skipping this entry."
        )
        benchmark_results[row["ID"]]["metadata"]["skipped"] = True
        benchmark_results[row["ID"]]["metadata"]["skipped_reason"] = (
            "target_document_not_found"
        )
        continue

    for query_type in query_columns:
        if query_type == "Noisy natural language query":
            query = row["Natural language query"]
            random.seed(129869)

            query = query.replace("[...]", " ")
            query = re.sub(r"[\[\]\.\,\:]", " ", query)
            query = query.lower()

            # Replace two or more white spaces through single whitespace
            plain_text = re.sub(r"\s+", " ", query).strip()

            query_tokens = query.split()
            query_tokens = [word for word in query_tokens if word not in stop_words_set]

            i = 0
            while i < len(query_tokens) - 1:
                if random.random() < 0.1:
                    temp_word = query_tokens[i]
                    query_tokens[i] = query_tokens[i + 1]
                    query_tokens[i + 1] = temp_word
                    i += 2  # Add 2 to avoid double swapping
                else:
                    i += 1

            query = " ".join(query_tokens)
            query = "".join([s for s in query if random.random() < 0.9])
        else:
            query = row[query_type]

        if not pd.isna(query):
            print(f'Searching: "{query}"')

            results_dict = search(
                query,
                collection,
                prompts,
                model,
                config,
                document_index,
                refine_query=config["benchmark_refine_query"],
                llm_output_cache=llm_output_cache,
            )
            results_list = search_results_to_docs(results_dict, solr, config)["results"]

            top_results = []
            for i, result in enumerate(results_list[:10]):
                distance = result.get("distance")
                doc_id = result.get("id")
                doc_src = result.get("src")
                doc_description = result.get("llm_description")
                doc_entity_kname = result.get("entity_kname")

                res = {
                    "rank": i + 1,
                    "distance": distance,
                    "id": doc_id,
                    "description": doc_description,
                    "entity_kname": doc_entity_kname,
                    "src": doc_src.split("proof")[0][:1000] + "...",
                }

                top_results.append(res)

            benchmark_results[row["ID"]]["queries"][query_type] = {
                "metrics": {
                    "top_k_accuracy": top_k_accuracy(results_list, target_identifier),
                    "normalized_discounted_cumulative_gain": normalized_discounted_cumulative_gain(
                        results_list, target_identifier
                    ),
                    "reciprocal_rank": reciprocal_rank(results_list, target_identifier),
                    "rank": rank(results_list, target_identifier),
                    "duration": round(results_dict["duration"] * 10)
                    / 10,  # Round to 1 decimal to avoid having a new duration for each benchmark run
                },
                "query": query,
                "refined_query": results_dict["refined_query"],
            }

benchmark_results["summary"] = calculate_mean_metrics(benchmark_results)
benchmark_llm_name = (
    results_suffix
    + "_"
    + config["vllm_name"].replace("/", "-")
    + "_"
    + config["llm_name"].replace("/", "-")
)

if not os.path.exists("./benchmark/results/"):
    os.makedirs("./benchmark/results/")

with open("./benchmark/results/" + benchmark_llm_name + ".json", "w") as outfile:
    json.dump(benchmark_results, outfile, indent=4)
