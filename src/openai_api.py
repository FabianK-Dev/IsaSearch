"""
openai_api.py: This file contains the helpers that are shared by all backends which talk to an
OpenAI compatible server, i.e. the "openai" LLM backend in src/llm.py and the "openai" embedding
backend in src/embeddings.py.

Both backends usually authenticate against the same server, thus the API key is resolved here
once instead of once per backend.
"""

import os

# Configuration keys that can hold a credential and thus must never be printed or logged.
SECRET_CONFIG_KEYS = ["openai_api_key"]


# An API key is a credential and must not be committed, thus config["openai_api_key_env"] only
# holds the *name* of the environment variable that contains the key. config["openai_api_key"]
# is supported as a fallback for setups in which an environment variable is inconvenient.
# Returns None if no API key is configured, which is the case for servers without authentication.
def openai_api_key(config):
    api_key_env = config.get("openai_api_key_env", "")

    if api_key_env:
        api_key = os.environ.get(api_key_env, "")

        # Failing here means that a missing API key is reported on startup instead of as an
        # HTTP 401 in the middle of a run that has already taken hours.
        if not api_key:
            raise RuntimeError(
                "The environment variable '"
                + api_key_env
                + "' configured at config['openai_api_key_env'] is not set or empty. Please export "
                + "the API key of the OpenAI compatible server, e.g. 'export "
                + api_key_env
                + "=<your-api-key>'."
            )

        return api_key

    return config.get("openai_api_key") or None


# Returns a copy of the configuration in which every credential is replaced by a placeholder, so
# that the configuration can be printed without leaking an API key that was set at
# config["openai_api_key"] into the console or a log file.
def config_without_secrets(config):
    return {
        key: "<redacted>" if key in SECRET_CONFIG_KEYS and value else value
        for key, value in config.items()
    }


# Servers without authentication can reject a request that carries an empty Authorization header,
# thus the header is only added if an API key is actually configured.
def openai_headers(api_key):
    if api_key:
        return {"Authorization": "Bearer " + api_key}

    return {}


# requests' raise_for_status() only reports the status code, but OpenAI compatible servers explain
# the actual problem (e.g. an exceeded context size or an unknown model) in the response body, thus
# both are part of the message. The API key is only ever sent in a header and is therefore never
# part of it. Kept separate from raising, because a retryable status is reported the very same way
# but through a different exception (see RetryableEmbeddingError in src/embeddings.py).
def status_error_message(response, description):
    return (
        description
        + " failed with status code "
        + str(response.status_code)
        + ": "
        + response.text
    )


def raise_for_status_with_body(response, description):
    if response.ok:
        return

    raise RuntimeError(status_error_message(response, description))
