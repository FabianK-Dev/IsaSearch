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

from flask import Flask, request, send_from_directory

from src.bootstrap import load_config, boot_components, DEFINITIONS_LOAD
from src.embeddings import search, search_results_to_docs


config = load_config()
# The definitions corpus is only attached, never built: building it informalizes every definition
# with the LLM, which takes hours and is done separately with 'python3 -m src.duplicates
# --build-corpus-only'. If it does not exist, definition search is simply not offered.
components = boot_components(config, definitions=DEFINITIONS_LOAD)

solr = components["solr"]
prompts = components["prompts"]
document_index = components["document_index"]
collection = components["collection"]
model = components["model"]
llm_output_cache = components["llm_output_cache"]

THEOREMS = "theorems"
DEFINITIONS = "definitions"


# The definition prompts are optional: if the prompts folder does not contain them, the theorem
# prompts are used for definitions as well.
def prompt_key(name):
    return name + "_definitions" if name + "_definitions" in prompts else name


# Every searchable corpus, i.e. its ChromaDB collection, its document index and the prompts to use.
corpora = {
    THEOREMS: {
        "collection": collection,
        "document_index": document_index,
        "retrieve_prompt_key": "retrieve",
        "search_refine_prompt_key": "search_refine",
    }
}

if components["definition_collection"] is not None:
    corpora[DEFINITIONS] = {
        "collection": components["definition_collection"],
        "document_index": components["definition_index"],
        "retrieve_prompt_key": prompt_key("retrieve"),
        "search_refine_prompt_key": prompt_key("search_refine"),
    }
    print("Definition search is enabled.")

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


# Report which optional features this server offers, so that the web UI can hide what is unavailable.
@app.get("/capabilities")
def capabilities_endpoint():
    return {"definition_search": DEFINITIONS in corpora}


# Serve the search endpoint at /
# 'query' is a mandatory string parameter and contains the user query
# 'refine_query' is an optional boolean parameter, that if left out resolves to true and enables/disables LLM query refinement
# 'kind' is an optional string parameter and selects the corpus to search, either 'theorems' (default) or 'definitions'
@app.get("/search")
def search_endpoint():
    query = request.args.get("query", "")
    refine_query = request.args.get("refine_query", "true").lower() == "true"
    kind = request.args.get("kind", THEOREMS).lower()
    print(f"Received search query: {query} (kind: {kind})")

    if kind not in [THEOREMS, DEFINITIONS]:
        return {
            "error": f"Unknown kind '{kind}', expected '{THEOREMS}' or '{DEFINITIONS}'."
        }, 400

    if kind not in corpora:
        return {
            "error": "Definition search is not available on this server. Build the definitions "
            "corpus with 'python3 -m src.duplicates --build-corpus-only' first."
        }, 503

    corpus = corpora[kind]

    # Search the given query with refine_query enabled/disabled and provide all loaded variables from above
    # search() returns a dict with document IDs only (instead of theorem source codes) to save RAM
    results_dict = search(
        query,
        corpus["collection"],
        prompts,
        model,
        config,
        corpus["document_index"],
        refine_query,
        llm_output_cache=llm_output_cache,
        retrieve_prompt_key=corpus["retrieve_prompt_key"],
        search_refine_prompt_key=corpus["search_refine_prompt_key"],
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
