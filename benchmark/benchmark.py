"""
benchmark.py: This file initializes all required components, i.e. Solr, tokenizer, prompts, document_index, document_descriptions, ChromaDB, LLM and LLM output cache and runs the benchmark based on the configuration and the benchmark.csv file. The beginning of the file is similar to app.py.

- Solr: connects to a running Solr database reachable at config["solr_core_url"]
- Tokenizer: loads the configured tokenizer model to calculate the maximum number of tokens required for all prompts
- Prompts: loads all prompts from prompts/ that will be fed to the embedding function and the LLM
- document_index: Builds the document_index, i.e. loads all documents (i.e. any theorem, lemma, corollary or proposition) from Solr and filters only necessary information (e.g. theorem source code, file name, session, etc.)
- document_descriptions: Loads or generates an informal description for each document using the configured LLM backend to allow more effective search with informal user queries
- ChromaDB: loads an embedding function from the configured pre-trained sentence transformer, creates a new or loads an existing ChromaDB collection and embeds any document that isn't already embedded
- LLM: Loads the configured LLM to refine user queries
- LLM cache: Loads an existing LLM output cache or creates a new one, if enabled.

Finally, for each metric the average will be calculated. All benchmark results will be saved to the results/ folder.
"""

from src.solr import connect_solr
from src.documents import build_document_index, get_document_descriptions
from src.embeddings import (
    search,
    search_results_to_docs,
    get_chromadb_collection,
    ensure_embedding_backend,
)
from src.llm import (
    load_prompts,
    get_llm,
    get_llm_output_cache,
    ensure_llm_backend,
    document_model_name,
    query_model_name,
)
from src.openai_api import config_without_secrets
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

print("Checking LLM backend and preparing configured models if required...")
ensure_llm_backend(config)

print("Checking embedding backend...")
ensure_embedding_backend(config)

print("Loading Solr...")
solr = connect_solr(config)

# Depending on the strategy that will be investigated, the benchmark result file suffix will change to distinguish the results.
results_suffix = ""
if config["add_metadata"]:
    results_suffix = results_suffix + "M"
    config["artifacts_folder"] = config["artifacts_folder"] + "-with-metadata"
    config["prompts_folder"] = config["prompts_folder"] + "-with-metadata"
    config["chroma_db_path"] = config["chroma_db_path"] + "-with-metadata"

if config["add_user_query"]:
    results_suffix = results_suffix + "U"

if config["benchmark_search_refine"]:
    results_suffix = results_suffix + "R"

if results_suffix == "":
    results_suffix = "baseline"

print("Using config for benchmark:")
# Printed without credentials, because config["openai_api_key"] can hold an API key.
pprint(config_without_secrets(config))

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(config["tokenizer_name"])

print("Loading prompts...")
prompts = load_prompts(config)

print("Building document index...")
document_index = build_document_index(config, solr)

print("Getting document descriptions...")
document_index = get_document_descriptions(config, document_index, prompts, tokenizer)

print("Deleting tokenizer object...")
del tokenizer
print("Finished deleting tokenizer object.")

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

random.seed(129869)

for i, row in tqdm(benchmark_df.iterrows(), total=len(benchmark_df)):
    # This is a list of dictionaries with potential valid theorems
    # That means, if a theorem in the search results matches the conditions of any dictionary in the list "target_identifier", the search result will be consider successful and metrics will be calculated accordingly in metrics.py.
    target_identifier = row["Target Identifier"]

    if row["ID"] not in benchmark_results:
        benchmark_results[row["ID"]] = {"metadata": {}, "queries": {}}

    # Skip the benchmark row, if the entry's cell at column "Skip" is set to "true"
    if row["Skip"] == "true":
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

    # If a target identifier is missing in the row in the benchmark.csv, we cannot confirm if any search result is a valid search result and thus have to skip this entry.
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

    # If the target identifier JSON string cannot be parsed, we cannot confirm if any search result is a valid search result and thus have to skip this entry.
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

    # Check if a theorem identified by a target identifier exists in the document index.
    target_exists = False
    print("Searching document identified by '" + row["Target Identifier"] + "'...")
    for doc_id in document_index:
        if is_correct_target(document_index[doc_id], target_identifier):
            target_exists = True
            break

    # If no valid target exists, then no search result will be considered valid and the search will always result in a negative result.
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

    # Do a search for each query type
    for query_type in query_columns:
        # If the query type is "Noisy natural language query", generate the noisy query based on the "Natural language query"
        if query_type == "Noisy natural language query":
            query = row["Natural language query"]

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
                refine_query=config["benchmark_search_refine"],
                llm_output_cache=llm_output_cache,
            )
            results_list = search_results_to_docs(results_dict, solr, config)["results"]

            # Add the top 10 results for a search to the benchmark results to allow examining the search results.
            # This is useful because in my paper I showcase different examples for search results to explain performance differences.
            top_results = []
            for i, result in enumerate(results_list[:10]):
                distance = result.get("distance")
                doc_id = result.get("id")
                doc_src = result.get("src")
                doc_description = result.get("llm_description")
                doc_entity_kname = result.get("entity_kname")

                if config["benchmark_add_top_results"]:
                    res = {
                        "rank": i + 1,
                        "distance": distance,
                        "id": doc_id,
                        "entity_kname": doc_entity_kname,
                        "embedding_string": doc_description.strip()
                        + "\n\n"
                        + doc_src.strip(),
                    }

                    top_results.append(res)

            # Calculate metrics using the methods from metrics.py
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
                "source": row["Natural language query source"],
                "refined_query": results_dict["refined_query"],
                "top_results": top_results,
            }

# Calculate the mean of all metrics and save the benchmark result.
benchmark_results["summary"] = calculate_mean_metrics(benchmark_results)
benchmark_model_name = (
    results_suffix
    + "_"
    + document_model_name(config).replace("/", "-")
    + "_"
    + query_model_name(config).replace("/", "-")
)

if not os.path.exists("./benchmark/results/"):
    os.makedirs("./benchmark/results/")

with open("./benchmark/results/" + benchmark_model_name + ".json", "w") as outfile:
    json.dump(benchmark_results, outfile, indent=4)
