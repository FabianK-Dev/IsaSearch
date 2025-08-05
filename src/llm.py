"""
llm.py: This file handles prompt loading, LLM initialization, and caching of generated outputs.
"""

import glob
import json
import os

from pathlib import Path

import torch
from gpt4all import GPT4All


# Load the prompts that will be used for the LLM and ChromaDB from the folder configured at config["prompts_folder"].
def load_prompts(config):
    prompts_folder = config["prompts_folder"]
    prompts = {}

    for file in glob.glob(prompts_folder + "/*.txt"):
        prompt_name = Path(file).stem

        with open(file, "r") as file:
            data = file.read()
            prompts[prompt_name] = data

    return prompts


# Saves LLM output to the cache folder, configured at config["cache_folder"].
def save_llm_output_cache(llm_output_cache, config):
    print("Saving LLM output cache...")

    CACHE_FOLDER = config["cache_folder"]
    LLM_OUTPUT_CACHE = f"{CACHE_FOLDER}/llm_output_cache.json"

    with open(LLM_OUTPUT_CACHE, "w") as file:
        json.dump(llm_output_cache, file, indent=4)


# Load the LLM used for search query refinement using GPT4All.
def get_llm(config):
    model = GPT4All(
        config["llm_name"],
        device="cuda" if torch.cuda.is_available() else "cpu",
        n_ctx=1024,
    )
    return model


# Load the LLM output from the cache folder, configured at config["cache_folder"].
def get_llm_output_cache(config):
    llm_output_cache = None
    if config["enable_llm_output_cache"]:
        CACHE_FOLDER = config["cache_folder"]
        LLM_OUTPUT_CACHE = f"{CACHE_FOLDER}/llm_output_cache.json"

        if not os.path.exists(LLM_OUTPUT_CACHE):
            print(
                "Warning: LLM output cache file '"
                + LLM_OUTPUT_CACHE
                + "' does not exist, thus a new one will be created."
            )
            llm_output_cache = {}
        else:
            print("Loading LLM output cache...")
            with open(LLM_OUTPUT_CACHE, "r") as file:
                data = file.read()
                llm_output_cache = json.loads(data)
                print("Finished loading LLM output cache.")
    else:
        print("LLM output caching is disabled in the config.")

    return llm_output_cache
