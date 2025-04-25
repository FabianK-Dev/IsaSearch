from sentence_transformers import SentenceTransformer, CrossEncoder, util

import torch
import os
import time

bi_encoder = None
cross_encoder = None

def load_encoders():
    global bi_encoder, cross_encoder

    bi_encoder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    bi_encoder.max_seq_length = 256*2
    cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')

def encode_embeddings(config, documents_tree):
    CACHE_FOLDER = config["cache_folder"]
    EMBEDDINGS_CACHE = f"{CACHE_FOLDER}/embeddings_cache.pt"

    # Retrieve and Rerank pipeline
    if not torch.cuda.is_available():
        print("No GPU found, so the CPU will be used instead which may increase encoding and search duration.")

    bi_encoder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    bi_encoder.max_seq_length = 256*2

    if os.path.exists(EMBEDDINGS_CACHE):
        encoded_embeddings = torch.load(EMBEDDINGS_CACHE)
        print("Finished loading cached embeddings.")
    else:
        encoded_embeddings = bi_encoder.encode(
            documents_tree["documents"],
            convert_to_tensor=True,
            show_progress_bar=True)
        torch.save(encoded_embeddings, EMBEDDINGS_CACHE)

    return encode_embeddings
