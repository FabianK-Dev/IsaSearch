"""
app.py: This module initializes all required components, i.e. Solr, tokenizer, prompts, document_index, document_descriptions, ChromaDB, LLM and LLM output cache and opens a Flask server that serves both the REST API and the web UI.

- Solr: connects to a running Solr database reachable at config["solr_core_url"]
- Tokenizer: loads the configured tokenizer model to calculate the maximum number of tokens required for all prompts
- Prompts: loads all prompts from prompts/ that will be fed to the embedding function and the LLM
- document_index: Builds the document_index, i.e. loads all documents (i.e. any theorem, lemma, corollary or proposition) from Solr and filters only necessary information (e.g. theorem source code, file name, session, etc.)
- document_descriptions: Loads or generates an informal description for each document using the configured LLM backend to allow more effective search with informal user queries
- ChromaDB: loads an embedding function from the configured pre-trained sentence transformer, creates a new or loads an existing ChromaDB collection and embeds any document that isn't already embedded
- LLM: Loads the configured LLM to refine user queries
- LLM cache: Loads an existing LLM output cache or creates a new one, if enabled.

Finally, Flask and package 'waitress' is used to serve both the REST API and static files (e.g. HTML, images, etc.).
Note: To simplify matters, from now on "theorem" will be used representatively for theorems, lemmas, corollaries and propositions in comment and docstrings.
"""

import json

from transformers import AutoTokenizer
from flask import Flask, request, send_from_directory

from src.solr import connect_solr
from src.documents import build_document_index, get_document_descriptions
from src.embeddings import (
    search,
    search_results_to_docs,
    get_chromadb_collection,
    ensure_embedding_backend,
)
from src.llm import load_prompts, get_llm, get_llm_output_cache, ensure_llm_backend
from src.installation import (
    check_and_update,
    build_index,
    setup_isabelle_components,
    get_isabelle_version,
)


print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

print("Checking LLM backend and preparing configured models if required...")
ensure_llm_backend(config)

print("Checking embedding backend...")
ensure_embedding_backend(config)

print("Checking, downloading or updating AFP if required...")
if config.get("check_for_updates", True):
    components = config.get("components", {})

    for key, comp_config in components.items():
        check_and_update(key, comp_config)

print("Setting up Isabelle components if required...")
setup_isabelle_components()
config["isabelle_version"] = get_isabelle_version()

print("Building Isabelle FindFacts index if required...")
build_index(config)

print("Loading Solr...")
solr = connect_solr(config)

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

    # Search the given query with refine_query enabled/disabled and provide all loaded variables from above
    # search() returns a dict with document IDs only (instead of theorem source codes) to save RAM
    results_dict = search(
        query,
        collection,
        prompts,
        model,
        config,
        document_index,
        refine_query,
        llm_output_cache=llm_output_cache,
    )
    # Next, use the returned document IDs from search() and receive the corresponding documents by their IDs (including all data, such as theorem source code) from Solr
    results_list = search_results_to_docs(results_dict, solr, config)

    return results_list


if __name__ == "__main__":
    print(
        f"Serving Flask API on port {config['api_port']}... Open: http://localhost:{config['api_port']}/"
    )
    # Import the package here (and not at the start of the file) because it is only loaded if this script is run directly
    # __name__ == "__main__" makes sure this condition is not True if app.py is imported (import src.app) => there is no need to open a flask server in that case
    from waitress import serve

    serve(app, host="0.0.0.0", port=config["api_port"], threads=1)
