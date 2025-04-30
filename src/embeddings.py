from sentence_transformers import SentenceTransformer, CrossEncoder, util

import torch
import os
import time

def load_models(bi_encoder_model, cross_encoder_model):
    bi_encoder = SentenceTransformer(bi_encoder_model)
    bi_encoder.max_seq_length = 256*2
    cross_encoder = CrossEncoder(cross_encoder_model)

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

def search(search_query, encoded_embeddings, bi_encoder, cross_encoder, document_tree):
    start = time.time()
    docs_to_retrieve = 1000

    # Bi-encoder search
    question_encoded = bi_encoder.encode(search_query, convert_to_tensor=True)
    question_encoded = question_encoded.cuda()

    hits = util.semantic_search(question_encoded, encoded_embeddings, top_k=docs_to_retrieve)
    hits = hits[0] # It is in theory possible to search multiple queries at once, however we only provided one search query and thus 'hits' only contains one element

    # Cross-encoder search
    cross_encoder_input = [[search_query, document_tree["documents"][hit['corpus_id']]] for hit in hits] # corpus_id is the index of the original document in documents
    cross_encoder_scores = cross_encoder.predict(cross_encoder_input)

    # Assign each cross encoder score to hits list
    for i in range(len(cross_encoder_scores)):
        hits[i]['cross_encoder_score'] = cross_encoder_scores[i]

    hits = sorted(hits, key=lambda x: x['cross_encoder_score'], reverse=True)
    results = []

    for hit in hits:
        results.append({
            "score": hit["cross_encoder_score"],
            "id": document_tree["document_ids"][hit['corpus_id']]
        })

    end = time.time()
    search_duration  = end - start
    print(f"Search time: {end - start} sec")

    return {
        "results": results[:100], # Only return the top 100 results
        "duration": search_duration
    }
