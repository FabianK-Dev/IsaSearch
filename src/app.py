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
llm_pipe, llm_args = get_llm(config)

print("Check if loading LLM output cache is enabled via config...")
llm_output_cache = get_llm_output_cache(config)

# results_dict = search(query, collection, prompts, llm_args, llm_pipe, config, llm_output_cache=llm_output_cache)
# results_list = search_results_to_docs(results_dict, document_tree)["results"]
