"""
This module initializes all required components, i.e. Solr, tokenizer, prompts, document_tree, document_descriptions, ChromaDB, LLM and LLM output cache

- Solr: connects to a running Solr database reachable at config["solr_core_url"]
- Tokenizer: loads the configured tokenizer model to calculate the maximum number of tokens required for all prompts
- Prompts: loads all prompts from prompts/ that will be fed to the embedding function and the LLM
- document_tree: Builds the document_tree, i.e. loads all documents (i.e. any theorem, lemma or corollary) from Solr and filters only necessary information (e.g. theorem source code, file name, session, etc.)
- document_descriptions: Loads or generates an informal description for each document using vLLM to allow more effective search with informal user queries
- ChromaDB: loads an embedding function from the configured pre-trained sentence transformer, creates a new or loads an existing ChromaDB collection and embeds any document that isn't already embedded
- LLM: Loads the configured LLM to refine user queries
- LLM cache: Loads an existing LLM output cache or creates a new one, if enabled.

Finally, Flask and package 'waitress' is used to serve both the rest API and static files (e.g. HTML)
"""

import json

import torch
from transformers import AutoTokenizer
from chromadb.utils import embedding_functions
from flask import Flask, request, send_from_directory

from src.solr import connect_solr
from src.documents import build_document_tree, get_document_descriptions
from src.embeddings import search, search_results_to_docs, get_chromadb_collection
from src.llm import load_prompts, get_llm, get_llm_output_cache


print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

print("Loading Solr...")
solr = connect_solr(config)

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(config["vllm_name"])

print("Loading prompts...")
prompts = load_prompts(config)

print("Building document tree...")
document_tree = build_document_tree(config, solr)

print("Getting document descriptions...")
document_tree = get_document_descriptions(config, document_tree, prompts, tokenizer)

# Clean up tokenizer to free up memory
del tokenizer

print("Loading ChromaDB embedding function...")
embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/multi-qa-distilbert-cos-v1",
    device="cuda" if torch.cuda.is_available() else "cpu",
)
print("Loading ChromaDB collection...")
collection = get_chromadb_collection(config, prompts, embedder, document_tree)

print("Loading LLM...")
model = get_llm(config)

print("Loading LLM output cache if enabled via config...")
llm_output_cache = get_llm_output_cache(config)

print("Preparing Flask app...")
app = Flask(__name__)


# Serve the front end, i.e. index.html at /
@app.route("/")
def web():
    return send_from_directory("html", "index.html")


# Serve other static files, e.g. images, stylesheets, etc.
@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("html", filename)


# Serve the search endpoint at /
# 'query' is a mandatory string parameter and contains the user query
# 'refine_query' is an optional boolean parameter, that if left out resolves to true and enables/disables LLM query refinement
@app.get("/search")
def search_endpoint():
    query = request.args.get("query", "")
    refine_query = request.args.get("refine_query", "true").lower() == "true"
    print(f"Received search query: {query}")

    # search
    results_dict = search(
        query,
        collection,
        prompts,
        model,
        config,
        document_tree,
        refine_query,
        llm_output_cache=llm_output_cache,
    )
    results_list = search_results_to_docs(results_dict, solr, config)

    return results_list


if __name__ == "__main__":
    print(
        f"Serving Flask API on port {config['api_port']}... Open: http://localhost:{config['api_port']}/"
    )
    # Import the package here (and not at the start of the file) because it is only loaded if this script is run directly
    from waitress import serve

    serve(app, host="0.0.0.0", port=config["api_port"], threads=1)
