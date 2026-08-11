"""
llm.py: This file handles prompt loading, LLM initialization, and caching of generated outputs.

Two LLM backends are supported and selected through config["llm_backend"]:
- "ollama": talks to a local Ollama server through its HTTP API.
- "llamacpp": talks to one or more local llama.cpp servers (llama-server) through their HTTP API.

This file is the only place that knows about backend specific configuration keys.
Other modules should use the backend agnostic helpers (get_llm, get_document_llm,
query_model_name, document_model_name, ensure_llm_backend) instead.
"""

import glob
import json
import os
import atexit
import subprocess
import time

from pathlib import Path
from urllib.parse import urlparse
import requests

OLLAMA_BACKEND = "ollama"
LLAMACPP_BACKEND = "llamacpp"

# All servers that were started by this application and thus need to be stopped on exit.
managed_processes = []


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


def ollama_is_running(base_url):
    try:
        response = requests.get(base_url.rstrip("/") + "/api/tags", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


def cleanup():
    while managed_processes:
        name, process = managed_processes.pop()
        print("Stopping " + name + " server started by this application...")
        process.terminate()


atexit.register(cleanup)


def start_ollama(base_url):
    parsed_url = urlparse(base_url)

    if parsed_url.hostname not in ["localhost", "127.0.0.1"]:
        raise RuntimeError(
            "Ollama is not reachable at "
            + base_url
            + " and can only be started automatically for localhost URLs."
        )

    print("Starting Ollama server...")
    try:
        managed_processes.append(
            (
                "Ollama",
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ),
            )
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Ollama command not found. Please install Ollama from https://ollama.com/download."
        ) from exc

    for _ in range(30):
        if ollama_is_running(base_url):
            print("Ollama is up and running.")
            return
        time.sleep(1)

    raise RuntimeError("Timed out while waiting for Ollama to start.")


def model_is_available(model_name, available_models):
    if model_name in available_models:
        return True

    if ":" not in model_name and model_name + ":latest" in available_models:
        return True

    return False


def ollama_models(base_url):
    response = requests.get(base_url.rstrip("/") + "/api/tags", timeout=10)
    response.raise_for_status()
    return {model["name"] for model in response.json().get("models", [])}


def pull_ollama_model(model_name):
    print("Pulling Ollama model '" + model_name + "'...")
    try:
        subprocess.run(["ollama", "pull", model_name], check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Ollama command not found. Please install Ollama from https://ollama.com/download."
        ) from exc


def ensure_ollama(config):
    base_url = config["ollama_base_url"]

    if not ollama_is_running(base_url):
        start_ollama(base_url)

    available_models = ollama_models(base_url)
    required_models = {
        config["ollama_document_model"],
        config["ollama_query_model"],
    }

    for model_name in required_models:
        if not model_is_available(model_name, available_models):
            pull_ollama_model(model_name)
            available_models = ollama_models(base_url)


# llama.cpp uses slightly different names than Ollama for the same sampling parameters,
# and expects them at the top level of the request instead of within an "options" object.
def llamacpp_options(config):
    sampling_parameters = config["sampling_parameters"]
    options = {
        "temperature": sampling_parameters["temperature"],
        "top_p": sampling_parameters["top_p"],
        "min_p": sampling_parameters["min_p"],
        "n_predict": sampling_parameters["max_tokens"],
    }

    # llama.cpp disables top_k sampling for values <= 0, so negative values are omitted instead of being passed through.
    if sampling_parameters["top_k"] >= 0:
        options["top_k"] = sampling_parameters["top_k"]

    if sampling_parameters.get("stop"):
        options["stop"] = sampling_parameters["stop"]

    return options


# llama-server answers /health with 503 while the model is still loading, so this doubles as a readiness check.
def llamacpp_is_running(base_url):
    try:
        response = requests.get(base_url.rstrip("/") + "/health", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


# A model can either be given as a path to a local GGUF file or as an 'hf:<repo>[:<quantization>]'
# specification, in which case llama-server downloads the model from Hugging Face on first start.
def llamacpp_model_arguments(model_spec):
    if model_spec.startswith("hf:"):
        return ["-hf", model_spec[len("hf:") :]]

    return ["-m", model_spec]


def start_llamacpp(base_url, model_spec, config):
    parsed_url = urlparse(base_url)

    if parsed_url.hostname not in ["localhost", "127.0.0.1"]:
        raise RuntimeError(
            "llama.cpp is not reachable at "
            + base_url
            + " and can only be started automatically for localhost URLs."
        )

    # The server is started on the port of the configured URL, which is also the port that is checked
    # for readiness and used for all requests. Guessing a port here would start a server that this
    # application then never reaches, so a missing port is rejected instead.
    if parsed_url.port is None:
        raise RuntimeError(
            "llama.cpp is not reachable at "
            + base_url
            + " and can only be started automatically for URLs with an explicit port, e.g. 'http://localhost:8080'."
        )

    port = parsed_url.port
    server_binary = config.get("llamacpp_server_binary", "llama-server")

    print(
        "Starting llama.cpp server for model '"
        + model_spec
        + "' on port "
        + str(port)
        + "..."
    )
    # llama.cpp logs verbosely to stderr, so its output is written to a log file within the cache folder
    # instead of the console. This keeps the log available if the server fails to start.
    log_file_path = config["cache_folder"] + "/llama-server-" + str(port) + ".log"
    if not os.path.exists(config["cache_folder"]):
        os.makedirs(config["cache_folder"])

    try:
        with open(log_file_path, "w") as log_file:
            llamacpp_process = subprocess.Popen(
                [server_binary, "--port", str(port)]
                + llamacpp_model_arguments(model_spec),
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "'"
            + server_binary
            + "' command not found. Please install llama.cpp from https://github.com/ggml-org/llama.cpp."
        ) from exc

    managed_processes.append(("llama.cpp", llamacpp_process))

    # Waiting for llama.cpp can take considerably longer than waiting for Ollama, because 'hf:' models
    # are downloaded on first start and loading a model into memory happens before the server is ready.
    for _ in range(600):
        if llamacpp_is_running(base_url):
            print("llama.cpp is up and running at " + base_url + ".")
            return

        # If the server exited (e.g. because the model does not exist or the port is already in use),
        # fail immediately instead of waiting for the full timeout.
        exit_code = llamacpp_process.poll()
        if exit_code is not None:
            raise RuntimeError(
                "The llama.cpp server for model '"
                + model_spec
                + "' exited with code "
                + str(exit_code)
                + " while starting. Please check '"
                + log_file_path
                + "' for the reason."
            )

        time.sleep(1)

    raise RuntimeError(
        "Timed out while waiting for llama.cpp to start. Please check '"
        + log_file_path
        + "' for details."
    )


# Two URLs can address the same server without being equal as strings (e.g. a trailing slash or
# '127.0.0.1' instead of 'localhost'), so URLs are compared by host and port instead.
def llamacpp_url_key(base_url):
    parsed_url = urlparse(base_url)
    default_port = 443 if parsed_url.scheme == "https" else 80
    hostname = parsed_url.hostname
    # 'localhost' and '127.0.0.1' address the same server, thus they are treated as equal.
    hostname = "127.0.0.1" if hostname == "localhost" else hostname

    return (hostname, parsed_url.port if parsed_url.port else default_port)


# A llama-server process serves exactly one model, so one server per configured model is required.
# If both models are identical, a single server at config["llamacpp_base_url"] serves both.
def llamacpp_servers(config):
    document_model = config["llamacpp_document_model"]
    query_model = config["llamacpp_query_model"]

    if document_model == query_model:
        return {config["llamacpp_base_url"]: query_model}

    query_base_url = config["llamacpp_base_url"]
    document_base_url = config["llamacpp_document_base_url"]

    if llamacpp_url_key(query_base_url) == llamacpp_url_key(document_base_url):
        raise RuntimeError(
            "config['llamacpp_base_url'] ('"
            + query_base_url
            + "') and config['llamacpp_document_base_url'] ('"
            + document_base_url
            + "') address the same server, but different models are configured. A llama.cpp server "
            + "serves a single model, so the two models need to be served on different ports."
        )

    return {query_base_url: query_model, document_base_url: document_model}


def ensure_llamacpp(config):
    for base_url, model_spec in llamacpp_servers(config).items():
        # A server that already answers at the configured URL is used as-is. llama-server provides no
        # reliable way to check which model it serves, so the configured model is assumed to be loaded.
        if not llamacpp_is_running(base_url):
            start_llamacpp(base_url, model_spec, config)


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


class LlamaCppLLM:
    def __init__(self, base_url, options):
        self.base_url = base_url.rstrip("/")
        self.options = options

    def generate(self, prompt):
        # The model is not part of the request, because a llama-server process always serves a single model.
        response = requests.post(
            self.base_url + "/completion",
            json={
                "prompt": prompt,
                "stream": False,
                **self.options,
            },
            timeout=None,
        )
        response.raise_for_status()
        return response.json()["content"]


# Returns the configured LLM backend and validates it, so that a typo fails early instead of silently falling back.
def llm_backend(config):
    backend = config.get("llm_backend", OLLAMA_BACKEND)

    if backend not in [OLLAMA_BACKEND, LLAMACPP_BACKEND]:
        raise ValueError(
            "Unknown LLM backend '"
            + str(backend)
            + "' configured at config['llm_backend']. Supported backends are '"
            + OLLAMA_BACKEND
            + "' and '"
            + LLAMACPP_BACKEND
            + "'."
        )

    return backend


# The model names are also used as cache keys and within benchmark result file names,
# so they have to be resolved for the configured backend.
def query_model_name(config):
    if llm_backend(config) == LLAMACPP_BACKEND:
        return config["llamacpp_query_model"]

    return config["ollama_query_model"]


def document_model_name(config):
    if llm_backend(config) == LLAMACPP_BACKEND:
        return config["llamacpp_document_model"]

    return config["ollama_document_model"]


# Starts the configured backend if required and makes sure that the configured models are available.
def ensure_llm_backend(config):
    if llm_backend(config) == LLAMACPP_BACKEND:
        ensure_llamacpp(config)
    else:
        ensure_ollama(config)


# The LLM that is used to refine search queries.
def get_llm(config):
    if llm_backend(config) == LLAMACPP_BACKEND:
        return LlamaCppLLM(
            config["llamacpp_base_url"],
            llamacpp_options(config),
        )

    return OllamaLLM(
        config["ollama_base_url"],
        config["ollama_query_model"],
        ollama_options(config),
    )


# The LLM that is used to informalize (i.e. describe) documents.
def get_document_llm(config):
    if llm_backend(config) == LLAMACPP_BACKEND:
        # Validate the server configuration, so that a misconfiguration is reported here as well and
        # not only when the servers are started.
        llamacpp_servers(config)

        # If both models are identical, a single server at config["llamacpp_base_url"] serves both.
        base_url = (
            config["llamacpp_base_url"]
            if config["llamacpp_document_model"] == config["llamacpp_query_model"]
            else config["llamacpp_document_base_url"]
        )

        return LlamaCppLLM(base_url, llamacpp_options(config))

    return OllamaLLM(
        config["ollama_base_url"],
        config["ollama_document_model"],
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
