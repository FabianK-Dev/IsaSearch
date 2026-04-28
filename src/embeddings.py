"""
embeddings.py: This file manages ChromaDB embeddings and semantic search with LLM-based query refinement and a caching mechanism.
"""

import os
import time
import torch
import chromadb
from chromadb.utils import embedding_functions


from src.solr import docs_by_ids
from src.llm import save_llm_output_cache


# This method loads an existing or creates a new ChromaDB collection and embeds all documents that haven't been embedded, yet.
def get_chromadb_collection(config, prompts, document_index):
    print("Loading ChromaDB embedding function...")
    mps_is_available = (
        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    )
    embedding_device = "mps" if mps_is_available else "cpu"
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=config["chroma_db_embedder"],
        device=embedding_device,
    )

    # ChromaDB path
    if not os.path.exists(config["chroma_db_path"]):
        os.makedirs(config["chroma_db_path"])

    # ChromaDB client and collection
    chroma_db_path = config["chroma_db_path"] + "/chroma_db"
    print("Loading ChromaDB collection at path '" + chroma_db_path + "'...")

    chroma_client = chromadb.PersistentClient(path=chroma_db_path)
    collection = chroma_client.get_or_create_collection(
        "afp_docs", embedding_function=embedder
    )

    # Get set of all already existing document IDs (saved at the source key)
    existing = set()
    metadata_response = collection.get(include=["metadatas"])

    if "metadatas" in metadata_response and metadata_response["metadatas"] is not None:
        for item in metadata_response["metadatas"]:
            existing.add(item["source"])

    print("Preparing documents before adding to ChromaDB collection...")
    filtered_index = [doc_id for doc_id in document_index if doc_id not in existing]
    print(f"{len(filtered_index)} documents are still missing in ChromaDB collection.")

    # Documents will be embedded in batches of 5000 documents each.
    for i in range(0, len(filtered_index), 5000):
        doc_ids = filtered_index[i : i + 5000]
        print(f"Processing documents {i} to {i + len(doc_ids)}...")

        doc_embeddings = []
        metadatas = []

        for doc_id in doc_ids:
            doc = document_index[doc_id]
            # Append an instruction before the document string, which improves the search quality in zero-shot situations.
            doc_src = doc["llm_description"].strip() + "\n\n" + doc["src"].strip()
            embedding_str = prompts["embed"].format(doc_src=doc_src)

            doc_embeddings.append(embedding_str)
            metadatas.append({"source": doc["id"]})

        collection.add(documents=doc_embeddings, ids=doc_ids, metadatas=metadatas)

    return collection


# This search(...) method does the following:
# 1. If enabled, refine the search query using a LLM. If config["enable_llm_output_cache"] is enabled, it will use cached responses for cached search queries.
# 2. Combine the original search query and LLM-refined search query to search the ChromaDB collection for the top 100 closest documents.
# 3. Finally, the top 100 search results with its LLM descriptions, the search duration and the refined query will be returned.
# Note, that in this step we only return result IDs with its LLM description. In search_results_to_docs() we will query Solr to retrieve the document source code, etc. for each result ID.
def search(
    search_query,
    collection,
    prompts,
    model,
    config,
    document_index,
    refine_query=True,
    llm_output_cache=None,
):
    start = time.time()
    cached_duration = None
    docs_to_retrieve = 100
    refined_query = None

    if refine_query:
        # Load the prompt that will be used as an instruction to the LLM to refine the search query
        llm_prompt = prompts["search_refine"].format(search_query=search_query)

        # Check if a cached response for the search query and prompt already exists
        if (
            llm_output_cache is not None
            and config["ollama_query_model"] in llm_output_cache
            and llm_prompt in llm_output_cache[config["ollama_query_model"]]
        ):
            print(f"Using cached LLM response for prompt '{llm_prompt[:200]}...'")
            refined_query = llm_output_cache[config["ollama_query_model"]][llm_prompt][
                "output"
            ]
            # If using a cached response, also use a cached duration (i.e. the original response generation duration).
            # Otherwise the duration would be very short for consecutive benchmark runs and would falsify the benchmark result.
            cached_duration = llm_output_cache[config["ollama_query_model"]][
                llm_prompt
            ]["output_duration"]
        else:
            # If config["enable_llm_output_cache"] is False, the method parameter llm_output_cache will be None. In that case reset it to an empty dictionary {} so we can write into it.
            llm_output_cache = llm_output_cache if llm_output_cache is not None else {}
            refined_query = model.generate(llm_prompt)

            end = time.time()
            output_duration = end - start

            if config["ollama_query_model"] not in llm_output_cache:
                llm_output_cache[config["ollama_query_model"]] = {}

            llm_output_cache[config["ollama_query_model"]][llm_prompt] = {
                "output": refined_query,
                "output_duration": output_duration,
            }

            if config["enable_llm_output_cache"]:
                save_llm_output_cache(llm_output_cache, config)

        try:
            refined_query = refined_query.split("<BEGIN>")[1]
            refined_query = refined_query.split("<END>")[0]
        except Exception:
            print(
                "Warning: Could not extract refined query using <BEGIN> and <END> from text generated by LLM for query '"
                + search_query
                + "', thus using it for search as is."
            )

        if config["add_user_query"]:
            search_query = search_query + "\n\n" + refined_query
        else:
            search_query = refined_query

        query_text = prompts["retrieve"].format(search_query=search_query)
    else:
        query_text = prompts["retrieve"].format(search_query=search_query)

    # Query the ChromaDB collection with the given query_text
    query_result = collection.query(
        query_texts=[query_text], n_results=docs_to_retrieve
    )
    results = {}

    # For each document retrieved, also add its LLM description and its ID
    for metadata, distance in zip(
        query_result["metadatas"][0], query_result["distances"][0]
    ):
        result_id = metadata["source"]
        results[result_id] = {
            "distance": distance,
            "id": result_id,
            "llm_description": document_index[result_id]["llm_description"],
        }

    end = time.time()
    search_duration = end - start

    if cached_duration is not None:
        search_duration = search_duration + cached_duration

    return {
        "results": results,
        "duration": search_duration,
        "refined_query": refined_query,
    }


# Given a list of search results with IDs, retrieve the documents from Solr.
# Additionaly this method adds a link to the original .thy-file in the repository at configured config["afp_remote_thys_folder_url"]
def search_results_to_docs(search_results, solr, config):
    ids = [_id for _id in search_results["results"]]

    for doc in docs_by_ids(solr, ids):
        doc_id = doc["id"]
        # Merge search_results with Solr documents
        search_results["results"][doc_id] = {**search_results["results"][doc_id], **doc}

        # Set default URLs to '#' which indicates the URL is not available
        search_results["results"][doc_id]["remote_url"] = "#"
        search_results["results"][doc_id]["entry_url"] = "#"
        search_results["results"][doc_id]["theory_url"] = "#"

        # Add direct link to the file in the remote repository and the entry URL
        # If the "ID" key starts with "USER_HOME", it's an entry from the AFP.
        # Otherwise, if it starts with "ISABELLE_HOME", it's a built-in theory file.
        # Then we can only add the link to the remote theory file (e.g. hosted on https://isabelle.in.tum.de/library/)
        if search_results["results"][doc_id]["id"].startswith("USER_HOME"):
            sub_path = search_results["results"][doc_id]["file"].split("/thys/")
            # If the file path does not contain /thys/ it means that the file does not exist in the repository
            if len(sub_path) > 1:
                # Add the line where the theorem code starts using #L... so that GitLab automatically jumps to the desired line when opening it in the browser
                search_results["results"][doc_id]["remote_url"] = (
                    config["afp_remote_thys_folder_url"]
                    + "/"
                    + sub_path[1]
                    + "#L"
                    + str(search_results["results"][doc_id]["start_line"])
                )

            # Extract the sub path for isa-afp.org
            sub_path = search_results["results"][doc_id]["url_path"].split("/")
            if len(sub_path) > 1:
                # We need the second last element from the URL path separated by /
                search_results["results"][doc_id]["entry_url"] = (
                    config["afp_remote_entry_url"] + "/" + sub_path[-2] + ".html"
                )
        else:
            # If it's a built-in theory file, we cannot add a remote or entry link, but we can add the link to the theory file (e.g. hosted on https://isabelle.in.tum.de/library/)
            sub_path = search_results["results"][doc_id]["url_path"]
            search_results["results"][doc_id]["theory_url"] = (
                config["isabelle_remote_theory_url"] + "/" + sub_path
            )

        # Remove HTML and XML from API response to lower response size and network usage
        del search_results["results"][doc_id]["html"]
        del search_results["results"][doc_id]["xml"]

    # Convert search_results["results"] to a list => this makes sorting or receiving the nth result easier
    search_results["results"] = [
        value for _, value in search_results["results"].items()
    ]
    return search_results
