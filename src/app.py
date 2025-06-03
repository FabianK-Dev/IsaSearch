from src.solr import connect_solr
from src.documents import build_document_tree, get_document_descriptions
from src.embeddings import search, search_results_to_docs
from src.llm import load_prompts
from benchmark.metrics import top_k_accuracy, normalized_discounted_cumulative_gain, reciprocal_rank, rank, calculate_mean_metrics, is_correct_target

from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from tqdm import tqdm
from pprint import pprint
from chromadb.utils import embedding_functions

import json
import pandas as pd
import chromadb
import os
import torch

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

print("Loading Solr...")
solr = connect_solr(config)

print("Using config for app:")
pprint(config)

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(config["llm_name"])

print("Loading prompts...")
prompts = load_prompts(config)

print("Building document tree...")
document_tree = build_document_tree(config, solr)

print("Clearing CUDA cache...")
torch.cuda.empty_cache()

print("Getting document descriptions...")
document_tree = get_document_descriptions(config, document_tree, prompts, tokenizer)

# ChromaDB embedding function
print("Loading embedding function...")
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="sentence-transformers/multi-qa-distilbert-cos-v1", device='cuda')
print("Finished loading embedding function.")

# ChromaDB path
if not os.path.exists(config["chroma_db_path"]):
    os.makedirs(config["chroma_db_path"])

# ChromaDB client and collection
chroma_db_path = config["chroma_db_path"] + "/chroma_db"
print("Loading ChromaDB client at path '" + chroma_db_path + "'...")

chroma_client = chromadb.PersistentClient(path=chroma_db_path)
collection = chroma_client.get_or_create_collection("afp_docs", embedding_function=embedder)

# Get set of all already existing document IDs (saved at the source key)
existing = set()
metadata_response = collection.get(include=["metadatas"])

if "metadatas" in metadata_response and metadata_response["metadatas"] is not None:
    for item in metadata_response["metadatas"]:
        existing.add(item["source"])

print("Preparing documents before adding to collection...")
filtered_tree = [doc_id for doc_id in document_tree if doc_id not in existing]

for i in range(0, len(filtered_tree), 5000):
    doc_ids = filtered_tree[i:i + 5000]
    print(f"Processing documents {i} to {i + len(doc_ids)}...")

    doc_embeddings = []
    metadatas = []

    for doc_id in doc_ids:
        doc = document_tree[doc_id]
        doc_src = doc["llm_description"].strip() + "\n\n" + doc["src"].strip()
        embedding_str = prompts["embed"].format(doc_src=doc_src)

        doc_embeddings.append(embedding_str)
        metadatas.append({"source": doc["id"]})

    #embeddings = embedder.encode(doc_embeddings, convert_to_tensor=True).cpu().numpy()
    collection.add(
        documents=doc_embeddings,
        ids=doc_ids,
        metadatas=metadatas)

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

try:
    while True:
        print()
        print("Please enter a search query or terminate the application using Ctrl + C:")
        print("Examples: 'pythagoras', 'pythagorean theorem but in vector space', 'fundamental formula for generating Pythagorean triples', ...")
        query = input("Query: ")

        results_dict = search(query, collection, prompts, generation_args, pipe, config, llm_output_cache=llm_output_cache)
        results_list = search_results_to_docs(results_dict, document_tree)["results"]

        top_results = []
        for i, result in enumerate(results_list[:10]):
            score = result.get("score")
            doc_id = result.get("id").split("/")[-1]

            src_text = result.get("src", "")
            doc_description = result.get("llm_description")
            doc_entity_kname = result.get("entity_kname")

            if len(src_text) > 500:
                src_text = src_text[:500] + "...\n(theorem source code truncated to 500 characters)"

            print(f"RESULT {i+1}: | SCORE (lower is better): {str(round(score, 3))} | ID: {doc_id}")
            print(src_text)
            print()
            print("LLM SUMMARY: " + doc_description)
            print()
            print("-" * 40)
except KeyboardInterrupt:
    print("\nApplication terminated by user.")
