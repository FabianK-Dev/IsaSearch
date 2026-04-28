"""
llm.py: This file handles prompt loading, LLM initialization, and caching of generated outputs.
"""

import glob
import json
import os

from pathlib import Path
import requests


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


def ollama_options(config):
    sampling_parameters = config["sampling_parameters"]
    options = {
        "temperature": sampling_parameters["temperature"],
        "top_p": sampling_parameters["top_p"],
        "min_p": sampling_parameters["min_p"],
        "num_predict": sampling_parameters["max_tokens"],
    }

    if sampling_parameters["top_k"] >= 0:
        options["top_k"] = sampling_parameters["top_k"]

    if sampling_parameters.get("stop"):
        options["stop"] = sampling_parameters["stop"]

    return options


class OllamaLLM:
    def __init__(self, base_url, model_name, options):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.options = options

    def generate(self, prompt):
        response = requests.post(
            self.base_url + "/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": self.options,
            },
            timeout=None,
        )
        response.raise_for_status()
        return response.json()["response"]


def get_llm(config):
    return OllamaLLM(
        config["ollama_base_url"],
        config["ollama_query_model"],
        ollama_options(config),
    )


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
