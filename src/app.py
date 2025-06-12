from src.solr import connect_solr
from src.documents import build_document_tree, get_document_descriptions
from src.embeddings import search, search_results_to_docs, get_chromadb_collection
from src.llm import load_prompts, get_llm, get_llm_output_cache

from transformers import AutoTokenizer
from tqdm import tqdm
from pprint import pprint
from chromadb.utils import embedding_functions
from flask import Flask, request, send_from_directory

import json
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

print("Getting document descriptions...")
document_tree = get_document_descriptions(config, document_tree, prompts, tokenizer)

print("Loading ChromaDB embedding function...")
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="sentence-transformers/multi-qa-distilbert-cos-v1", device="cuda" if torch.cuda.is_available() else "cpu")
print("Loading ChromaDB collection...")
collection = get_chromadb_collection(config, prompts, embedder, document_tree)

print("Loading LLM pipeline and generation arguments...")
model = get_llm(config, prompts, tokenizer)

print("Check if loading LLM output cache is enabled via config...")
llm_output_cache = get_llm_output_cache(config)

print("Preparing Flask app...")
app = Flask(__name__)

@app.route("/")
def web():
    return send_from_directory("html", "index.html")

@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("html", filename)

@app.get("/search/<query>")
def search_endpoint(query):
    refine_query = request.args.get("refine_query", "true").lower() == "true"
    results_dict = search(query, collection, prompts, model, config, document_tree, refine_query, llm_output_cache=llm_output_cache)
    results_list = search_results_to_docs(results_dict, solr, config)
    return results_list

if __name__ == "__main__":
    print(f"Serving Flask API on port {config['api_port']}... Open: http://localhost:{config['api_port']}/")
    from waitress import serve
    serve(app, host="0.0.0.0", port=config["api_port"])
