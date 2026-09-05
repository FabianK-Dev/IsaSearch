# IsaSearch for Isabelle/Scala

An Isabelle2025-2 component for semantic search, corpus construction, duplicate
analysis and the paper's benchmarks. The Python implementation and browser UI
remain available in the parent project. This component exposes an HTTP API and
command-line tools. Scala runtime dependencies come exclusively from Isabelle,
including its bundled Solr/Lucene. It neither starts nor installs model servers.

## Register and compile

From the repository root, with Isabelle2025-2 on `PATH`:

```sh
isabelle components -u "$PWD/isabelle"
isabelle scala_build
isabelle isasearch_search -?
```

Keep the source component in this repository: its build bundles the existing
`benchmark/benchmark.csv` from the parent directory, which remains the dataset's
source of truth. Compilation uses `etc/build.props`; registered Scala tools use
a FindFacts-style launcher to include Isabelle's Solr classpath. No sbt, Maven,
Python, or extra JVM libraries are needed at Scala runtime.

AFP registration is needed only for building new content. Register an existing
AFP2025-2 installation with `isabelle components -u /path/to/afp` (registering its
`thys` directory works as well). Discovery uses `AFP.BASE`, `AFP.main_dir`, and
Isabelle's session structure, not a hard-coded checkout path. AFP metadata is
read from the registered root using Isabelle's TOML reader. Searching an imported
index, benchmarking it, or analyzing duplicates does not need AFP installed.

## Migrate the running Python index

Stop corpus updates for the entire export. Searches may continue. Use the Python
environment from the deployment and its actual configuration:

```sh
python -m src.export_index -c config.json -o /data/isasearch-export
isabelle isasearch_import -f /data/isasearch-export -i migrated
```

The exporter reads Chroma's public collection API, existing source caches,
description artifacts, and Solr metadata. It does not import inference backends
or regenerate descriptions or vectors. Solr must be reachable. Missing or stale
records, changed embedding inputs, invalid vectors, or collection changes fail
the export. The destination must not already exist. Use `--kind theorems` or
`--kind definitions` to restrict it.

The export includes actual collection metrics and dimensions, exact stored
embedding inputs, float32 vectors, prompts, model identity, source checksums,
descriptions and source metadata. Historical configuration must still describe
the collection; persisted model/truncation settings are checked where Chroma
provides them. For legacy collections without that evidence, the export records
the supplied configuration and query startup checks reference vectors. A full
production migration still needs an export from the deployed server.

See [the interchange specification](INTERCHANGE.md). Imports validate into a new
generation and publish only after all corpora succeed. Failed imports preserve
the previous generation. Native Solr approximate ranking may differ from Chroma;
reported cosine distance and squared Euclidean distance are computed from the
retained vectors, independently of Lucene's scores.

## Configure inference and search

Copy `etc/config.example.json` and adjust URLs and model names. Relative paths
are resolved against that configuration file. Its example prompt path assumes
it stays in `etc`; use an absolute prompt path when moving it elsewhere.

For search without a generative LLM, leave `llm_backend` as `none`. An embedding
service is still required. A user-managed CPU embedding server can expose an
OpenAI-compatible `/v1/embeddings` endpoint; configure its base URL and give it
the same model identity, tokenizer, pooling, normalization, and truncation as
the index. Endpoint aliases must match the model name recorded in the manifest.
The client validates dimensions and re-embeds reference inputs before querying.
A mismatch is an error rather than silently returning invalid similarities.

```sh
export ISASEARCH_API_KEY='your-server-key'
isabelle isasearch_search -c /path/to/config.json -i migrated 'a finite union of countable sets'
isabelle isasearch_search -c /path/to/config.json -i migrated -k definitions 'a partial order'
isabelle isasearch_server -c /path/to/config.json -i migrated -p 5001
```

Omit `openai_api_key_env` for a server that does not require authentication.
Credentials stay on the server and are not included in indexes or data components.
The API binds to loopback; use an authenticated reverse proxy for remote access.

| Backend | Generation configuration | Embeddings configuration |
| --- | --- | --- |
| `openai` | `openai_base_url`, `openai_document_model`, `openai_query_model` | `openai_embedding_base_url`, `openai_embedding_model` |
| `ollama` | `ollama_base_url`, `ollama_document_model`, `ollama_query_model` | `ollama_base_url`, `openai_embedding_model` or `embedding_model` |
| `llamacpp` | `llamacpp_base_url`, optional `llamacpp_document_base_url`, `llamacpp_document_model`, `llamacpp_query_model` | OpenAI-compatible embedding endpoint and settings |

Set `llm_backend` and `embedding_backend` independently. Generation uses
`sampling_parameters`; provider extensions use `openai_extra_body`,
`ollama_options`, and `llamacpp_extra_body`. Embedding extensions use
`embedding_extra_body`. Mandatory model/input/stream fields take precedence.
Ollama sends `truncate=false`; recorded client-side character truncation governs
embedding inputs. It never downloads a model. Python's in-process
sentence-transformers backend must be served through an HTTP embedding endpoint
for Scala use.

Common limits have configuration owners: `llm_request_timeout` (600 seconds),
`inference_connect_timeout` (10), `inference_health_timeout` (10), `llm_attempts`
and `embedding_attempts` (3), `openai_embedding_batch_size` (32),
`openai_embedding_max_characters` (8000 for newly built indexes), and
`capability_refresh_seconds` (30). Imported indexes retain their own truncation
contract. `embedding_reference_tolerance` defaults to 0.001 relative squared
error. HTTP 429 and transient server/transport errors are retried with bounded
backoff. Failed, empty, or truncated completions are not cached.

## HTTP API

- `GET /capabilities` returns `corpora`, `definition_search`,
  `embedding_available`, `embedding_error`, `query_expansion`, and
  `query_expansion_error`.
- `GET /search?query=...&kind=theorems&refine_query=false` returns `results`,
  `duration`, `refined_query`, plus `elapsed_duration` and `cache_hit`.
  Results retain source fields, descriptions, links, and distances. Exact
  embedding inputs and internal description artifacts are not exposed.
- `kind` is `theorems` or `definitions`. Query expansion defaults to off. Enabling
  it concatenates the original and expanded queries. An explicit request fails
  with HTTP 503 if the configured query LLM is unavailable; it never silently
  runs a different strategy. Invalid parameters return 400.

Capability state is refreshed periodically and updated after inference failures.
Model availability is checked through real inference, not just the existence of
a configured URL. Search and API startup never build a corpus.

## Build and resume

```sh
isabelle isasearch_index -c /path/to/build-config.json -i plain Example-Submission
isabelle isasearch_index -c /path/to/metadata-config.json -i metadata Example-Submission
```

Building requires a document LLM and embedder. Set `add_metadata` to false or true
in the respective configurations. Keep `prompts_folder` set to the base folder:
metadata builds append `-with-metadata`, matching the Python benchmark workflow
(for example, `qwen3-gemma` becomes `qwen3-gemma-with-metadata`). Select explicit
session arguments or `isabelle_sessions`; `all-AFP` and `all` use Isabelle session discovery.
`isabelle_excluded_sessions` removes sessions. `solr_query` and
`solr_query_definitions` override command selection; defaults are in
`etc/corpus_defaults.json`.

The pipeline builds Isabelle sessions, extracts blocks through FindFacts,
informalizes selected source, then embeds description plus source. Prompts come
from `prompts_folder`; document/query models are independent. Metadata variants
are fixed at build time. Use `-n` only when session build databases are already
current; it skips the session build, not extraction or consistency checks.

All generated data lives beneath `$ISABELLE_HOME_USER/isasearch`, apart from the
standard session databases and FindFacts source index in their Isabelle-managed
locations. Build concurrency is bounded by `llm_concurrency`. Each finished
description is saved before embedding, then the document/vector pair is saved.
Reruns reuse progress keyed by configuration, prompts, sessions, and source
metadata. Changed inputs invalidate the corresponding cache. A per-index lock
prevents competing corpus builds. Index generations publish atomically; existing
readers retain their opened generation. Old generations and progress are retained
for recovery and may be removed manually once no readers need them.

Pruning more than half of a previously indexed corpus requires the explicit
configuration `allow_large_prune: true`. Review session selection first. Empty
corpora are omitted; an entirely empty index is rejected.

## Distribute indexes

```sh
isabelle isasearch_index_build -i migrated -D /path/to/components
isabelle components -u /path/to/components/isasearch_migrated-YYYYMMDD
```

The tool creates an Isabelle data component with a compressed `File_Store`
database and settings. Ship this directory alongside the code component. For a
bundled index, place the generated `migrated.db` under the code component's
`lib/indexes/`. Users select it with `-i migrated`. Distribution archives are
immutable: first use extracts into the writable user directory, then opens
read-only Lucene readers. No generative model is needed to extract or use a
prebuilt corpus. Configuration and inference caches are not packaged.

## Duplicate analysis

```sh
isabelle isasearch_duplicates -c /path/to/config.json -i migrated -k all -x -e Example-Submission
isabelle isasearch_duplicates -c /path/to/config.json -i migrated -k definitions -N 10 -J
```

Use repeated `-e` for explicit entries, `-N` for newest entries by indexed dates,
`-x` for cross-kind matching, `-J` to disable judging, and `-a` to include every
candidate. Default selection is definitions. Cross-kind matching requires
compatible embedding contracts. Same-entry results are excluded; self-retrieval
checks and syntactic evidence are reported independently. Without a usable query
LLM, reports contain vector/syntactic evidence only.

Defaults match Python: `dedup_top_k=10`, `dedup_distance_threshold=0.3`,
`dedup_strong_distance_threshold=0.05`, `dedup_syntactic_threshold=0.9`, and
`dedup_max_judged_per_item=3`. Reports use Markdown and JSON under the user reports
directory or `-D`. Distances are metric-specific; thresholds must be interpreted
with the selected index's metric.

## Benchmarks

```sh
isabelle isasearch_benchmark -c /path/to/config.json -i plain -m metadata -s all
isabelle isasearch_benchmark -c /path/to/config.json -i plain -s baseline -f /path/to/benchmark.csv -D /path/to/results
```

Indexes must already exist. Strategies are `baseline` (original), `R`
(expanded), `UR` (concatenated), and their metadata variants `M`, `MR`, `MUR`.
Comma-separated strategies are supported. Manifest metadata flags and expansion
availability are validated before execution. No configuration files are rewritten
and no corpus caches are deleted. Scraping remains in the Python implementation.

The runner handles multiline CSV and JSON targets, skip annotations, missing
targets, title/natural/noisy queries, and Python's Hit@10, NDCG, reciprocal rank,
rank, and sample counts. It preserves the existing JSON structure and labels.
Noise uses CPython-compatible seeded randomness (`benchmark_seed`, default
129869) and fixed English stopwords, with no NLTK downloads. Set
`benchmark_add_top_results` for top-ten details.

Each result has a `.run.json` companion recording index/dataset checksums,
recipe, sanitized configuration, seed, cache policy, and actual query timings.
Legacy duration includes replayed cached generation time for comparison;
`elapsed_duration` records measured execution and `cache_hit` identifies replay.
Set `enable_llm_output_cache=false` for uncached model execution.

## Development and validation

```sh
isabelle scala_build
python -m unittest tests.test_scala_component -v
```

Python is used only for exporter and cross-language development tests. Tests use
real temporary Chroma collections and deterministic local HTTP stubs; the AFP
integration uses the registered `Example-Submission` session. No real model is
contacted. User settings and components are isolated in temporary directories.

Application choices use enums in `src/domain.scala`; parsing and serialization
happen at CLI, configuration, and JSON boundaries. Protocol field names remain
strings. Isabelle supplies JSON, TOML, options, session discovery, HTTP serving,
Solr (including its multiline CSV reader), and File_Store. Compatibility
algorithms absent from the bundled API (CPython RNG and SequenceMatcher) are
local and covered by Python golden comparisons. Scala sources follow the
manual layout of Isabelle and FindFacts; see [the style guide](STYLE.md).
