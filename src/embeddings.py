from sentence_transformers import SentenceTransformer, CrossEncoder, util
from src.solr import docs_by_ids

import torch
import os
import time

def encode_embeddings(config, documents_tree, bi_encoder):
    CACHE_FOLDER = config["cache_folder"]
    EMBEDDINGS_CACHE = f"{CACHE_FOLDER}/embeddings_cache.pt"

    # Retrieve and Rerank pipeline
    if not torch.cuda.is_available():
        print("No GPU found, so the CPU will be used instead which may increase encoding and search duration.")

    if os.path.exists(EMBEDDINGS_CACHE):
        encoded_embeddings = torch.load(EMBEDDINGS_CACHE)
        print("Finished loading cached embeddings.")
    else:
        encoded_embeddings = bi_encoder.encode(
            documents_tree["documents"],
            convert_to_tensor=True,
            show_progress_bar=True)

        # Double check in case that the .cache folder already exists, but the entry_db_cache.json does not exist
        if not os.path.exists(CACHE_FOLDER):
            os.makedirs(CACHE_FOLDER)

        torch.save(encoded_embeddings, EMBEDDINGS_CACHE)

    return encoded_embeddings

def search(search_query, collection, prompts):
    start = time.time()
    docs_to_retrieve = 10
    instruction = ""

    query_result = collection.query(
        query_texts=[instruction + "\n" + search_query],
        n_results=docs_to_retrieve
    )
    results = {}

    for metadata, distance in zip(query_result["metadatas"][0], query_result["distances"][0]):
        result_id = metadata["source"]
        results[result_id] = {
            "score": distance,
            "id": result_id
        }

    end = time.time()
    search_duration  = end - start
    print(f"Search time: {end - start} sec")

    return {
        "results": results,
        "duration": search_duration
    }

def search_results_to_docs(search_results, solr):
    result_ids = []
    for result_id in search_results["results"]:
        result_ids.append(result_id)

    result_documents = docs_by_ids(solr, result_ids) # Get the Solr documents for each search result by ID i.e. map each search result that only consists of an ID so far to its corresponding Solr document

    # Finally, update the search_results list and append data of the Solr document
    for result in result_documents:
        search_results["results"][result["id"]]["doc"] = result

    # Convert search_results["results"] to a list => this makes sorting or receiving the nth result easier
    search_results["results"] = [value for _, value in search_results["results"].items()]
    return search_results
