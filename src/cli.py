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

print("Using config for app:")
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
llm_pipe, llm_args = get_llm(config)

print("Check if loading LLM output cache is enabled via config...")
llm_output_cache = get_llm_output_cache(config)

class color:
   PURPLE = '\033[95m'
   CYAN = '\033[96m'
   DARKCYAN = '\033[36m'
   BLUE = '\033[94m'
   GREEN = '\033[92m'
   YELLOW = '\033[93m'
   RED = '\033[91m'
   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'
   END = '\033[0m'

try:
    while True:
        print()
        print(color.BOLD + color.RED + "Please enter a search query or terminate the application using Ctrl + C:")
        print("Examples: 'pythagoras', 'pythagorean theorem but in vector space', 'fundamental formula for generating Pythagorean triples', ..." + color.END)
        query = input("Query: ")

        results_dict = search(query, collection, prompts, llm_args, llm_pipe, config, llm_output_cache=llm_output_cache)
        results_list = search_results_to_docs(results_dict, document_tree)["results"]

        print()
        print(color.YELLOW + "REFINED QUERY USING LLM:")
        print(results_dict["refined_query"] + color.END)

        with open("user_queries.txt", "a") as myfile:
            myfile.write(query + "\n")

        top_results = []
        for i, result in enumerate(results_list[:10]):
            score = result.get("score")
            doc_id = result.get("id").split("/")[-1]

            src_text = result.get("src", "")
            doc_description = result.get("llm_description")
            doc_entity_kname = result.get("entity_kname")

            if len(src_text) > 500:
                src_text = src_text[:500] + "...\n(theorem source code truncated to 500 characters)"

            print(color.BLUE + f"RESULT {i+1}: | SCORE (lower is better): {str(round(score, 3))} | ID: {doc_id}" + color.END)
            print(color.CYAN + src_text + color.END)
            print()
            print(color.YELLOW + "LLM SUMMARY: " + doc_description + color.END)
            print()
            print("-" * 40)
except KeyboardInterrupt:
    print("\nApplication terminated by user.")
    print()
    print(color.BOLD + color.GREEN + "Thank you for testing the application!")
    print("Your search queries have been saved to user_queries.txt. Of course, they will not be uploaded or shared with anyone, however if you would like to help us improve this AI search, feel free to send the user_queries.txt file to F.Kadlez@campus.lmu.de. The user queries will be treated anonymously only and will be used in a benchmark to evaluate and improve the search performance.")

    print("user_queries.txt:")
    if os.path.exists("user_queries.txt"):
        with open("user_queries.txt", "r") as file:
            data = file.read()
            print(data)