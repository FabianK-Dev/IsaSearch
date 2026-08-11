# IsaSearch

This repository provides an AI-assisted semantic theorem search for the Archive of Formal Proofs using sentence-transformers, ChromaDB and LLMs. Additionally, it contains our benchmark data and results.

## Requirements

- [Python](https://www.python.org/downloads/) 3.11.2 or higher
- [pip](https://pip.pypa.io/en/stable/installation/) 23.0.1 or higher
- [git](https://git-scm.com/downloads) 2.47.3 or higher
- [Docker](https://www.docker.com/get-started) 29.2.1 or higher
- One of the supported LLM backends:
  - [Ollama](https://ollama.com/download) (default), or
  - [llama.cpp](https://github.com/ggml-org/llama.cpp) with `llama-server` available on the `PATH`

## Setup

### Quickstart

> ⚠️ **Warning:** Please run the following commands **inside the root folder of the repository** (this is necessary to ensure files like `config.json` are loaded correctly):

```bash
python3 -m venv .venv  # If this command does not work, please install the `venv` module for Python: `pip install venv`
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m src.app
```

The application starts Ollama automatically and pulls the configured models if they are missing.

**Note on Indexing Time:**
Building the full FindFacts index for the entire Archive of Formal Proofs takes about 24 hours, informalizing all theorems ~25 hours, and embedding them into ChromaDB ~2 hours.

**Default Test Configuration:**
> ⚠️ **Warning:** To allow for immediate testing, the default `config.json` is restricted to only two sessions:

```json
"isabelle_sessions": ["Ramsey-Infinite", "Ordinals_and_Cardinals"]
```

If you want to search the entire AFP, you need to update the `isabelle_sessions` list in `config.json` to include all desired sessions (or use `["all"]` if supported by your setup), but be prepared for the significant processing time mentioned above.

### LLM backend

The LLM backend is selected with `"llm_backend"` in `config.json` and is either `"ollama"` (default), `"llamacpp"` or `"openai"`:

| Backend | Configuration keys |
| --- | --- |
| `ollama` | `ollama_base_url`, `ollama_document_model`, `ollama_query_model` |
| `llamacpp` | `llamacpp_server_binary`, `llamacpp_base_url`, `llamacpp_document_base_url`, `llamacpp_document_model`, `llamacpp_query_model` |
| `openai` | `openai_base_url`, `openai_document_model`, `openai_query_model`, `openai_api_key_env` |

For `llamacpp`, a model is either a path to a local GGUF file (e.g. `/models/Phi-3.5-mini-instruct-Q4_K_M.gguf`) or a Hugging Face specification of the form `hf:<repo>[:<quantization>]` (e.g. `hf:bartowski/Phi-3.5-mini-instruct-GGUF:Q4_K_M`), which llama.cpp downloads automatically on first start.

For localhost URLs the application starts the required `llama-server` processes automatically and stops them again on exit. A `llama-server` process serves exactly one model, so if the document and query model differ, two servers are started: the query model at `llamacpp_base_url` and the document model at `llamacpp_document_base_url`. If a server is already running at a configured URL, it is used as-is.

The `openai` backend targets local inference servers that offer an OpenAI compatible `/chat/completions` endpoint, e.g. a remote `llama-server`, vLLM or LM Studio. Note that the sampling parameters `min_p` and `top_k` are sent as additional top level fields, which those servers accept but the hosted API at `api.openai.com` rejects. `openai_base_url` includes the API prefix (e.g. `http://10.153.73.66:8082/v1`), and `openai_document_model` and `openai_query_model` are the model names that the server expects. Prompts are sent as a single user message, so the server applies the chat template of the model itself and the prompts of this backend must not contain model specific markers such as `<|user|>`. Servers of this backend are never started automatically; only their reachability is checked on startup.

Refined queries are cached per model name, so switching the backend regenerates them. Document descriptions are only regenerated when a theorem's source code changes, so already informalized theorems keep the descriptions of the backend that generated them.

### Embedding backend

The embedding backend is selected with `"embedding_backend"` in `config.json` and is either `"sentence_transformers"` (default) or `"openai"`:

| Backend | Configuration keys |
| --- | --- |
| `sentence_transformers` | `chroma_db_embedder` |
| `openai` | `openai_embedding_base_url`, `openai_embedding_model`, `openai_embedding_batch_size`, `openai_embedding_max_characters`, `openai_api_key_env` |

With `sentence_transformers` the configured model is loaded locally and runs on MPS, CUDA or the CPU. With `openai` all embeddings are requested from the `/embeddings` endpoint of an OpenAI compatible server, e.g. a `llama-server` that was started with `--embeddings` on a GPU machine, and no local embedding model is loaded at all. Documents are sent in batches of `openai_embedding_batch_size` texts per request, because ChromaDB passes all documents of one `collection.add(...)` call to the embedding function at once.

Each text is truncated to `openai_embedding_max_characters` characters (8000) beforehand. This is required because llama.cpp rejects an input that does not fit into a single physical batch instead of truncating it, and a theorem including its proof can exceed that limit — a single long theorem would otherwise abort every indexing run at the same document.

> ⚠️ **Warning:** Isabelle source code tokenizes at roughly 3 characters per token, and at only about 2 for symbol-heavy theorems, so the default of 8000 characters can become close to 4000 tokens. The embedding server has to be started with a physical batch size of at least 4096, which is far above `llama-server`'s default of 512:
> ```bash
> llama-server -m Qwen3-Embedding-4B-Q8_0.gguf --embeddings --pooling last --alias Qwen3-Embedding-4B -c 16384 -ub 4096 -b 4096 --host 0.0.0.0 --port 8081
> ```
> Alternatively, lower `openai_embedding_max_characters` to match a smaller batch size.

> ⚠️ **Warning:** Changing the embedding model requires a fresh `chroma_db_path`. Embeddings of different models have different dimensions and ChromaDB cannot mix them within a single collection. For the same reason, changing the LLM that informalizes theorems requires a fresh `artifacts_folder`, because existing descriptions are only regenerated when a theorem's source code changes.

### API key

If the OpenAI compatible server requires authentication, set `"openai_api_key_env"` to the name of the environment variable that holds the key and export it before starting the application:

```bash
export ISASEARCH_API_KEY=<your-api-key>
```

The key is sent as an `Authorization: Bearer` header to the LLM server as well as to the embedding server. Setting `"openai_api_key"` directly in `config.json` works too, but keeps the credential within the repository; it is redacted whenever the configuration is printed. Leave both keys out for servers without authentication.

### Finding duplicated definitions

`python3 -m src.duplicates` answers the question whether the material of an AFP entry already exists elsewhere in the Archive of Formal Proofs. It was built for the experiment proposed by an AFP maintainer: take the *n* newest AFP entries, search for their definitions in the AFP, and ignore the definitions of the entry itself.

No re-indexing and no separate ingestion of a submission is needed. Isabelle's FindFacts indexes *every* command block of a theory, so the definitional commands are already in the Solr index; only `"solr_query"` filtered them out so far. The duplicate detection therefore adds a second corpus on top of the same Solr index, built from `"solr_query_definitions"`, with its own document index cache (`.cache/definition_index.json`), its own LLM descriptions (`artifacts/<model>/definition_descriptions.json`) and its own ChromaDB collection (`afp_definitions`). The theorem corpus is never modified.

Building that corpus is the expensive part, because every definition has to be informalized by the LLM once. Do it separately, it is resumable and prints the number of definitions before the first LLM call:

```bash
python3 -m src.duplicates --build-corpus-only
```

Afterwards the experiment itself is cheap:

```bash
python3 -m src.duplicates --newest 10
```

Useful options:

| Option | Effect |
| --- | --- |
| `--entry NAME` | analyse this entry instead of the newest ones, may be repeated |
| `--kinds all` | analyse definitions *and* theorems (`--kinds theorems` for theorems only) |
| `--no-llm-judge` | switch the LLM adjudication off, see below |
| `--all-candidates` | report the closest candidates of *every* document, not only those reaching a tier |
| `--report-dir DIR` | override the report location |

Reports are written to `reports/duplicates/experiment_<timestamp>.md` and `.json`.

#### Analysing a new submission

The tool analyses entries that are part of the index. For a submission that is not in the AFP mirror yet, put it into `afp/thys/<Entry>/`, add its session to `"isabelle_sessions"` in `config.json` and start the application once so that the existing FindFacts index build picks it up. Afterwards run `python3 -m src.duplicates --entry <Entry> --kinds all`. The entry's own definitions and theorems are always excluded from its own results, so only counterparts elsewhere in the AFP are reported, which you can then compare manually.

#### Switching the LLM adjudication off

The core of the analysis is a plain loop: every definition (and, with `--kinds all`, every theorem) of the analysed entry is used as an IsaSearch query against the rest of the AFP, and the closest counterparts are reported with their distance and a syntactic similarity. The LLM adjudication is an optional layer on top that asks the configured LLM whether a pair really is a duplicate. Switch it off with `--no-llm-judge` (or `"dedup_llm_judge": false`) to get the plain, deterministic search results; no candidate then reaches the `likely` tier and the report says so. Combine it with `--all-candidates` to see the raw ranking for every document, unfiltered by any threshold.

Note that the LLM is still needed to *build* the corpus, because every definition is informalized once before it is embedded.

Every candidate is reported in one of three tiers, configured in `config.json`:

| Tier | Meaning |
| --- | --- |
| `near-exact` | distance ≤ `dedup_strong_distance_threshold` or syntactic similarity ≥ `dedup_syntactic_threshold` |
| `likely` | the LLM judged the pair to be a duplicate |
| `possible` | distance ≤ `dedup_distance_threshold` |

Further keys are `dedup_top_k` (candidates per definition), `dedup_llm_judge` (adjudication on by default), `dedup_max_judged_per_item` (LLM calls per definition) and `dedup_report_folder`.

Two controls are part of every run and are included in the report. First, before its own entry is excluded, each definition must retrieve *itself* at a distance of about 0; if more than 5 % fail to do so, the run exits with a non-zero status because the corpus and the queries are then not in the same embedding space. Second, definitions of different entries that define something of the same base name and whose sources are nearly identical are collected syntactically and used as a ground truth, which yields a recall value for the semantic search.

Please keep in mind that semantic similarity is not logical duplication: the tiers are a triage aid for a human reviewer, not a verdict. The same holds for the LLM verdicts, which is why the report always contains the model's justification. Also note that meaningful results require an index of the whole AFP — with only the two sessions that are enabled for testing, almost nothing can be found.

### Tests

The tests use only the Python standard library's `unittest`, so they need no additional packages. Run them inside the root folder of the repository:

```bash
python3 -m unittest discover -s tests -t .
```

`tests/test_openai_backends.py` runs offline against a stub server and needs neither a network nor a GPU machine. `tests/test_server_availability.py` talks to the servers configured in `config.json`: it checks that both are reachable, that the configured models answer, and that the embedding server accepts a document of `openai_embedding_max_characters` as well as a full batch of `openai_embedding_batch_size` — which is what catches a physical batch size that is too small. It needs the API key exported and is skipped automatically when the backends are not set to `openai`. To run it alone:

```bash
python3 -m unittest tests.test_server_availability -v
```

### Benchmark

To run the Benchmark, use `python3 -m benchmark.benchmark` inside the root folder of the repository. If you want to run a full benchmark that compares different strategies (as discussed in our paper), run `run_full_benchmark.sh`.

**Important:** The results generated with the default configuration will differ from the paper. This is because the test setup only indexes the two sessions mentioned above (`"Ramsey-Infinite"`, `"Ordinals_and_Cardinals"`), whereas the paper results are based on the complete Archive of Formal Proofs.

## Screenshot

Below you can find a screenshot of the web UI:

## Pre-Commit hooks

This project uses [ruff](https://pypi.org/project/ruff/) and other pre-commit hooks to maintain code quality.

When continuing development, please install the hooks:

```bash
pre-commit install
```
