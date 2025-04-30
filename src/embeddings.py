from sentence_transformers import SentenceTransformer, CrossEncoder, util
from src.solr import docs_by_ids

import torch
import os
import time

def load_models(bi_encoder_model, cross_encoder_model=None):
    print(f"Loading bi-encoder {bi_encoder_model} ...")
    bi_encoder = SentenceTransformer(bi_encoder_model)
    bi_encoder.max_seq_length = 256*2

    if cross_encoder_model:
        cross_encoder = CrossEncoder(cross_encoder_model)
    else:
        cross_encoder = None
        print("Skip loading cross-encoder because no argument passed to method.")

    return bi_encoder, cross_encoder

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

def search(search_query, encoded_embeddings, document_tree, bi_encoder, cross_encoder=None):
    start = time.time()
    docs_to_retrieve = 1000

    # Bi-encoder search
    question_encoded = bi_encoder.encode(search_query, convert_to_tensor=True)
    question_encoded = question_encoded.cuda()

    hits = util.semantic_search(question_encoded, encoded_embeddings, top_k=docs_to_retrieve)
    hits = hits[0] # It is in theory possible to search multiple queries at once, however we only provided one search query and thus 'hits' only contains one element

    # Cross-encoder search is optional
    if cross_encoder:
        cross_encoder_input = [[search_query, document_tree["documents"][hit['corpus_id']]] for hit in hits] # corpus_id is the index of the original document in documents
        cross_encoder_scores = cross_encoder.predict(cross_encoder_input)

        # Assign each cross encoder score to hits list
        for i in range(len(cross_encoder_scores)):
            hits[i]['cross_encoder_score'] = cross_encoder_scores[i]

        hits = sorted(hits, key=lambda x: x['cross_encoder_score'], reverse=True)
    else:
        # If no cross_encoder model is given, sort the hits by bi_encoder
        hits = sorted(hits, key=lambda x: x['score'], reverse=True)

    results = {}

    for i, hit in enumerate(hits):
        if i >= 100: # Only return the top 100 results
            break

        result_id = document_tree["document_ids"][hit['corpus_id']]
        results[result_id] = {
            "score": hit["cross_encoder_score"] if cross_encoder else hit["score"],
            "id": result_id
        }

    end = time.time()
    search_duration  = end - start
    print(f"Search time: {end - start} sec")

    return {
        "results": results, # Only return the top 100 results
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
