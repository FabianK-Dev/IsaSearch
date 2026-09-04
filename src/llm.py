"""
llm.py: This file handles prompt loading, LLM initialization, and caching of generated outputs.

Three LLM backends are supported and selected through config["llm_backend"]:
- "ollama": talks to a local Ollama server through its HTTP API.
- "llamacpp": talks to one or more local llama.cpp servers (llama-server) through their HTTP API.
- "openai": talks to any OpenAI compatible server (e.g. a remote llama-server, vLLM or LM Studio)
  through its /chat/completions endpoint.

This file is the only place that knows about backend specific configuration keys.
Other modules should use the backend agnostic helpers (get_llm, get_document_llm,
query_model_name, document_model_name, ensure_llm_backend) instead.
"""

import glob
import json
import os
import atexit
import subprocess
import tempfile
import time

from pathlib import Path
from urllib.parse import urlparse
import requests

from src.openai_api import openai_api_key, openai_headers, raise_for_status_with_body

OLLAMA_BACKEND = "ollama"
LLAMACPP_BACKEND = "llamacpp"
OPENAI_BACKEND = "openai"

SUPPORTED_BACKENDS = [OLLAMA_BACKEND, LLAMACPP_BACKEND, OPENAI_BACKEND]

# The LLM output cache of the web application. The duplicate detection uses its own file (see
# config["dedup_llm_cache"]), because both are meant to run at the same time and the cache is
# rewritten as a whole: sharing one file would make the process that saves last silently drop
# everything the other one cached since it started.
DEFAULT_LLM_OUTPUT_CACHE = "llm_output_cache.json"

# How long a single completion request may take, overridable through config["llm_request_timeout"].
# Without a timeout a server that accepts the connection but never answers blocks the caller for as
# long as the process lives. That is fatal for the web application, which serves with a single
# thread: one wedged request would freeze the site until the process is restarted by hand. The
# default is generous, because informalizing a long theorem on a busy server is genuinely slow.
DEFAULT_LLM_REQUEST_TIMEOUT = 600


def llm_request_timeout(config):
    return config.get("llm_request_timeout", DEFAULT_LLM_REQUEST_TIMEOUT)


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


# The prompts ask the model to wrap its actual answer in these markers, so that the reasoning or
# the pleasantries around it can be cut away.
BEGIN_MARKER = "<BEGIN>"
END_MARKER = "<END>"


# Extract the part of an LLM output that the prompt asked for, i.e. what stands between the markers.
# Returns (text, found), where 'found' reports whether an opening marker was present at all, so that
# every caller can keep its own way of reporting a model that did not follow the prompt. A marker
# that is missing is not an error here: the surrounding text is usually still usable, which is why
# all callers fall back to it.
def extract_marked_output(raw_output):
    text = raw_output
    found = BEGIN_MARKER in text

    if found:
        text = text.split(BEGIN_MARKER, 1)[1]

    if END_MARKER in text:
        text = text.split(END_MARKER, 1)[0]

    return text, found


# Returns the path of an LLM output cache. 'cache_name' selects the cache file, so that entry points
# which run next to each other (the web application and the duplicate detection) can each own their
# own file. Two processes must never share one, because the cache is rewritten as a whole below.
def llm_output_cache_path(config, cache_name=DEFAULT_LLM_OUTPUT_CACHE):
    return f"{config['cache_folder']}/{cache_name}"


# Saves LLM output to the cache folder, configured at config["cache_folder"].
#
# The file is written to a temporary file next to it first and then moved into place, because
# os.replace() is atomic within a folder. A crash (or a full disk) during the write therefore leaves
# the previous cache intact instead of a truncated file that fails to parse on the next start.
def save_llm_output_cache(
    llm_output_cache, config, cache_name=DEFAULT_LLM_OUTPUT_CACHE
):
    print("Saving LLM output cache...")

    cache_path = llm_output_cache_path(config, cache_name)
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)

    # The temporary file has to live in the same folder as the cache, because os.replace() is only
    # atomic within a single file system.
    descriptor, temporary_path = tempfile.mkstemp(
        dir=os.path.dirname(cache_path) or ".", suffix=".tmp"
    )

    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump(llm_output_cache, file, indent=4)

        os.replace(temporary_path, cache_path)
    except BaseException:
        # Leaving a stray temporary file behind would accumulate over time, so it is removed on
        # every failure, including a KeyboardInterrupt during a long informalization run.
        if os.path.exists(temporary_path):
            os.remove(temporary_path)

        raise


# The sampling parameters of config["sampling_parameters"], translated for one backend. Every
# backend understands the same five settings but names the token limit differently, which is what
# 'max_tokens_key' selects. Keeping this in one place means a new sampling parameter is added once
# instead of once per backend.
def sampling_options(config, max_tokens_key):
    sampling_parameters = config["sampling_parameters"]
    options = {
        "temperature": sampling_parameters["temperature"],
        "top_p": sampling_parameters["top_p"],
        "min_p": sampling_parameters["min_p"],
        max_tokens_key: sampling_parameters["max_tokens"],
    }

    # llama.cpp and the OpenAI compatible servers disable top_k sampling for values <= 0, so negative
    # values are omitted instead of being passed through.
    if sampling_parameters["top_k"] >= 0:
        options["top_k"] = sampling_parameters["top_k"]

    if sampling_parameters.get("stop"):
        options["stop"] = sampling_parameters["stop"]

    return options


def ollama_options(config):
    return sampling_options(config, "num_predict")


# Returns whether the server at 'base_url' answers 'path' with HTTP 200. The timeout is short,
# because this only ever asks whether a server is up, never for any actual work.
def server_answers(base_url, path):
    try:
        response = requests.get(base_url.rstrip("/") + path, timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False


# A server of these backends is started as a child process of this application, so it can only ever
# be started on this machine. A remote URL therefore means the server has to be running already.
def require_local_url(base_url, name):
    if urlparse(base_url).hostname not in ["localhost", "127.0.0.1"]:
        raise RuntimeError(
            name
            + " is not reachable at "
            + base_url
            + " and can only be started automatically for localhost URLs."
        )


def ollama_is_running(base_url):
    return server_answers(base_url, "/api/tags")


def cleanup():
    while managed_processes:
        name, process = managed_processes.pop()
        print("Stopping " + name + " server started by this application...")
        process.terminate()


atexit.register(cleanup)


def start_ollama(base_url):
    require_local_url(base_url, "Ollama")

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
    return sampling_options(config, "n_predict")


# llama-server answers /health with 503 while the model is still loading, so this doubles as a readiness check.
def llamacpp_is_running(base_url):
    return server_answers(base_url, "/health")


# A model can either be given as a path to a local GGUF file or as an 'hf:<repo>[:<quantization>]'
# specification, in which case llama-server downloads the model from Hugging Face on first start.
def llamacpp_model_arguments(model_spec):
    if model_spec.startswith("hf:"):
        return ["-hf", model_spec[len("hf:") :]]

    return ["-m", model_spec]


def start_llamacpp(base_url, model_spec, config):
    require_local_url(base_url, "llama.cpp")
    parsed_url = urlparse(base_url)

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


# The OpenAI API names the token limit "max_tokens" and expects all sampling parameters at the top
# level of the request instead of within an "options" object.
def openai_options(config):
    # "min_p" and "top_k" are not part of the OpenAI API, but the OpenAI compatible endpoints of
    # local inference servers such as llama.cpp, vLLM and LM Studio accept them as additional top
    # level fields, which keeps the sampling configuration identical across all backends. Note that
    # the hosted API at api.openai.com rejects unknown parameters with HTTP 400 instead of ignoring
    # them, so those two entries have to be removed to target it.
    options = sampling_options(config, "max_tokens")

    # Anything else the configured server needs, merged verbatim into the request body. This exists
    # because the settings that matter most to a local server are the ones the OpenAI API never
    # standardised. The one this project depends on turns a reasoning model's thinking off:
    #
    #   "openai_extra_body": {"chat_template_kwargs": {"enable_thinking": false}}
    #
    # A model that thinks spends its entire token budget on reasoning and returns an empty
    # completion, so without this the corpus is built out of empty descriptions. Merged last, so
    # that a server specific setting can also override one of the values above.
    options.update(config.get("openai_extra_body", {}))

    return options


def ensure_openai(config):
    base_url = config["openai_base_url"].rstrip("/")
    headers = openai_headers(openai_api_key(config))

    print("Checking OpenAI compatible LLM server at " + base_url + "...")

    # Unlike Ollama and llama.cpp, a server of this backend is never started automatically, because
    # it usually runs on a different machine. Only its reachability is checked here, so that a wrong
    # URL or a missing API key fails on startup instead of in the middle of a run.
    try:
        response = requests.get(base_url + "/models", headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise RuntimeError(
            "The OpenAI compatible server at "
            + base_url
            + " is not reachable ("
            + str(exc)
            + "). Servers of the '"
            + OPENAI_BACKEND
            + "' backend are never started automatically, please make sure it is running and reachable."
        ) from exc

    raise_for_status_with_body(response, "Requesting the model list from " + base_url)

    try:
        available_models = {
            model.get("id") for model in response.json().get("data", [])
        }
    except ValueError:
        available_models = set()

    # Only a warning and not an error, because some servers report an internal model name or nothing
    # at all instead of the alias that has to be sent within a request.
    if available_models:
        for model_name in {
            config["openai_document_model"],
            config["openai_query_model"],
        }:
            if model_name not in available_models:
                print(
                    "Warning: model '"
                    + model_name
                    + "' is not listed at "
                    + base_url
                    + "/models. Available models are: "
                    + ", ".join(sorted(str(name) for name in available_models))
                    + "."
                )

    print("The OpenAI compatible server at " + base_url + " is up and running.")


class OllamaLLM:
    def __init__(
        self, base_url, model_name, options, timeout=DEFAULT_LLM_REQUEST_TIMEOUT
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.options = options
        self.timeout = timeout

    def generate(self, prompt, extra_options=None):
        response = requests.post(
            self.base_url + "/api/generate",
            json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {**self.options, **(extra_options or {})},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["response"]


class LlamaCppLLM:
    def __init__(self, base_url, options, timeout=DEFAULT_LLM_REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.options = options
        self.timeout = timeout

    def generate(self, prompt, extra_options=None):
        # The model is not part of the request, because a llama-server process always serves a single model.
        response = requests.post(
            self.base_url + "/completion",
            json={
                "prompt": prompt,
                "stream": False,
                **self.options,
                **(extra_options or {}),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["content"]


class OpenAILLM:
    def __init__(
        self,
        base_url,
        model_name,
        options,
        api_key=None,
        timeout=DEFAULT_LLM_REQUEST_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.options = options
        self.headers = openai_headers(api_key)
        self.timeout = timeout

    def generate(self, prompt, extra_options=None):
        # The prompt is sent as a single user message, because the server applies the chat template
        # of the model itself. Prompts for this backend therefore must not contain model specific
        # markers such as '<|user|>', which would end up as literal text within the message.
        response = requests.post(
            self.base_url + "/chat/completions",
            json={
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                **self.options,
                **(extra_options or {}),
            },
            headers=self.headers,
            timeout=self.timeout,
        )
        raise_for_status_with_body(
            response, "Generating a completion at " + self.base_url
        )

        choice = response.json()["choices"][0]
        content = choice["message"]["content"]

        # "length" means the model was stopped at max_tokens instead of finishing, which leaves the
        # description cut off mid-sentence - and embedded that way, silently, unless it is reported.
        # Servers that do not report a reason are taken at their word that the completion is whole.
        if choice.get("finish_reason") == "length":
            raise TruncatedCompletionError(
                "The completion was cut off at max_tokens ("
                + str(self.options.get("max_tokens"))
                + "). Raise config['sampling_parameters']['max_tokens'].",
                content,
            )

        return content


# Raised when a completion was cut off at max_tokens rather than ending on its own. Its own type,
# because the retry loop treats it differently from a refusal: a truncated description is damaged
# but still usable, so the last one is kept rather than discarded.
class TruncatedCompletionError(RuntimeError):
    def __init__(self, message, output):
        super().__init__(message)
        self.output = output


# Number of attempts per completion. The embedding side has retried from the start (see
# EMBEDDING_ATTEMPTS in src/embeddings.py); the LLM side did not, and a single failed request was
# enough to end an informalization run that had been going for days.
LLM_ATTEMPTS = 3

# The temperature of every attempt after the first. The configured sampling is usually greedy
# (temperature 0), which makes a run reproducible but also makes a failure reproducible: a server
# that rejects what its model produced - a completion cut off at max_tokens no longer parses as the
# chat format, for instance - rejects the identical output again on a plain retry. Perturbing the
# temperature is what gives the next attempt a different completion to return.
RETRY_TEMPERATURE = 0.3


# Generate a completion, retrying a failure a few times before giving up.
#
# Retrying covers both kinds of failure a server produces: a transient one (a dropped connection, a
# 503 while a model is loading), which the same request survives, and a deterministic one, which it
# does not - hence the temperature above. The exception of the last attempt is raised, so a caller
# that cannot go on still sees why.
def generate_with_retries(model, prompt, attempts=LLM_ATTEMPTS):
    last_error = None

    for attempt in range(attempts):
        try:
            extra_options = {} if attempt == 0 else {"temperature": RETRY_TEMPERATURE}
            return model.generate(prompt, extra_options)
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as exc:
            last_error = exc

            if attempt + 1 < attempts:
                # Backoff, so that a server which is briefly overloaded is given time rather than
                # the same burst of requests again. A truncated completion is not the server's
                # fault and needs no pause, only another sample that might end on its own.
                if not isinstance(exc, TruncatedCompletionError):
                    time.sleep(2**attempt)

    # A completion that only ever came back truncated is still returned: it is cut off at the end
    # but carries most of what it should, which is better for search than no description at all.
    # The caller counts these (see generate_document_descriptions) so a run reports how many of its
    # descriptions are damaged instead of embedding them silently.
    if isinstance(last_error, TruncatedCompletionError):
        raise TruncatedCompletionError(
            f"Every one of {attempts} attempts was cut off at max_tokens: {last_error}",
            last_error.output,
        ) from last_error

    raise RuntimeError(
        f"Generating a completion failed after {attempts} attempts: {last_error}"
    ) from last_error


# Returns the configured LLM backend and validates it, so that a typo fails early instead of silently falling back.
def llm_backend(config):
    backend = config.get("llm_backend", OLLAMA_BACKEND)

    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(
            "Unknown LLM backend '"
            + str(backend)
            + "' configured at config['llm_backend']. Supported backends are "
            + ", ".join("'" + name + "'" for name in SUPPORTED_BACKENDS)
            + "."
        )

    return backend


# The two roles an LLM is used in. Both are served by the same backend but usually by a different
# model, and every backend names its two models 'config["<backend>_<role>_model"]'.
QUERY_ROLE = "query"
DOCUMENT_ROLE = "document"


# The model names are also used as cache keys and within benchmark result file names,
# so they have to be resolved for the configured backend.
def model_name(config, role):
    return config[f"{llm_backend(config)}_{role}_model"]


def query_model_name(config):
    return model_name(config, QUERY_ROLE)


def document_model_name(config):
    return model_name(config, DOCUMENT_ROLE)


# Starts the configured backend if required and makes sure that the configured models are available.
def ensure_llm_backend(config):
    backend = llm_backend(config)

    if backend == LLAMACPP_BACKEND:
        ensure_llamacpp(config)
    elif backend == OPENAI_BACKEND:
        ensure_openai(config)
    else:
        ensure_ollama(config)


# The URL the llama.cpp server that serves the model of the given role listens at. A llama-server
# process serves a single model, so which URL that is follows from the server allocation of
# llamacpp_servers instead of being decided again here.
def llamacpp_role_base_url(config, role):
    if role == QUERY_ROLE:
        return config["llamacpp_base_url"]

    # Looking the URL up in the allocation also validates the server configuration, so that a
    # misconfiguration is reported here as well and not only when the servers are started.
    document_model = config["llamacpp_document_model"]

    return next(
        base_url
        for base_url, model_spec in llamacpp_servers(config).items()
        if model_spec == document_model
    )


# The LLM of one role, built for the configured backend.
def build_llm(config, role):
    backend = llm_backend(config)
    timeout = llm_request_timeout(config)

    if backend == LLAMACPP_BACKEND:
        # The model is not part of a llama.cpp request, so the role only selects the URL.
        return LlamaCppLLM(
            llamacpp_role_base_url(config, role), llamacpp_options(config), timeout
        )

    if backend == OPENAI_BACKEND:
        # A single OpenAI compatible server can serve more than one model, so unlike llama.cpp the
        # roles only differ by the model name and not by the URL they are requested at.
        return OpenAILLM(
            config["openai_base_url"],
            model_name(config, role),
            openai_options(config),
            openai_api_key(config),
            timeout,
        )

    return OllamaLLM(
        config["ollama_base_url"],
        model_name(config, role),
        ollama_options(config),
        timeout,
    )


# The LLM that is used to refine search queries.
def get_llm(config):
    return build_llm(config, QUERY_ROLE)


# The LLM that is used to informalize (i.e. describe) documents.
def get_document_llm(config):
    return build_llm(config, DOCUMENT_ROLE)


# The cache nests by model and then by prompt, so that switching the configured model never reuses
# an output that a different model generated. The two helpers below are the only places that know
# this layout; callers hold on to the returned entry, whose "output" and "output_duration" keys are
# part of the on-disk format that save_llm_output_cache writes.
def cached_output(cache, model_key, prompt):
    return cache.get(model_key, {}).get(prompt)


def store_output(cache, model_key, prompt, output, duration):
    cache.setdefault(model_key, {})[prompt] = {
        "output": output,
        "output_duration": duration,
    }


# Load the LLM output from the cache folder, configured at config["cache_folder"].
def get_llm_output_cache(config, cache_name=DEFAULT_LLM_OUTPUT_CACHE):
    llm_output_cache = None
    if config["enable_llm_output_cache"]:
        LLM_OUTPUT_CACHE = llm_output_cache_path(config, cache_name)

        if not os.path.exists(LLM_OUTPUT_CACHE):
            print(
                "Warning: LLM output cache file '"
                + LLM_OUTPUT_CACHE
                + "' does not exist, thus a new one will be created."
            )
            llm_output_cache = {}
        else:
            print(f"Loading LLM output cache from {LLM_OUTPUT_CACHE}...")
            with open(LLM_OUTPUT_CACHE, "r") as file:
                data = file.read()
                llm_output_cache = json.loads(data)
                print("Finished loading LLM output cache.")
    else:
        print("LLM output caching is disabled in the config.")

    return llm_output_cache
