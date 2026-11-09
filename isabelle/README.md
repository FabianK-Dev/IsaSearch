# IsaSearch component

An Isabelle2026 component for semantic search over the AFP and the Isabelle distribution, with
a website, an HTTP API, index builds, duplicate analysis and the paper's benchmarks. All Scala
dependencies come from Isabelle, including its Solr/Lucene; no sbt, Maven or extra JVM libraries
are needed. The `isasearch_*` tools run, as the FindFacts tools do, in a JVM of their own with
Isabelle's Solr classpath (`lib/scripts/isasearch`).

| Tool | Purpose |
| --- | --- |
| `isasearch_import` | install a released index, an exported generation or interchange data |
| `isasearch_search` | search from the command line (JSON output) |
| `isasearch_server` | website and HTTP API |
| `isasearch_index` | build an index from Isabelle sessions |
| `isasearch_export`, `isasearch_index_build`, `isasearch_prune` | distribute and clean up indexes |
| `isasearch_duplicates` | duplicate analysis of AFP entries |
| `isasearch_benchmark`, `isasearch_compare` | the paper's benchmark and comparisons of runs |
| `isasearch_test`, `isasearch_integration_test` | tests |

`isabelle isasearch_search '-?'` lists the options of the tools (quoted, because zsh expands an
unquoted `-?` as a file pattern).

The component also holds the prompts (`prompts`), the benchmark dataset and the paper's
results (`benchmark`), the configurations of index runs (`runs`), the website (`web`) and the
reference outputs of its tests (`tests/goldens.json`).

## Install

```sh
isabelle components -u "$PWD/isabelle"
isabelle isasearch_import
```

The first tool call compiles the component (`isabelle scala_build`). See
[QUICKSTART.md](../QUICKSTART.md) for requirements and a first search.

An AFP is needed only to build indexes and to link results to local files. Register it with
`isabelle components -u /path/to/afp` (its `thys` directory works as well).

## Indexes

Indexes live by name in `$ISASEARCH_HOME_USER/indexes/NAME` (by default
`~/.isabelle/Isabelle2026/isasearch`). Tools select one with `-i NAME`; the default is the
Isabelle option `isasearch_index`, `plain`, the name of the released index.

Each build or import publishes a new *generation* atomically. Running servers switch to it
with their next request and close the old one when its last request ends. Old generations stay
until `isasearch_prune -i NAME` removes them. A failed build or import leaves the current
generation in place.

### Released indexes

`isasearch_import` without `-f` installs a release from GitHub (option `isasearch_releases`):

- with a registered AFP, the newest release of its revision;
- with `-R TAG`, that release;
- otherwise it lists the releases and asks. Without a terminal, it fails and lists them.

The parts are downloaded to `$ISASEARCH_HOME_USER/downloads/TAG`, checked against
`SHA256SUMS`, unpacked and installed; the directory is removed afterwards. Complete parts of an
interrupted download are kept and not downloaded again. No external `zstd` or `tar` is needed.

Releases are made by [`admin/update`](admin/README.md).

### Export and import

```sh
isabelle isasearch_export -i plain -D /path/to/directory
isabelle isasearch_import -f /path/to/directory/isasearch-plain -i plain
```

`isasearch_export` writes the current generation as it is, with checksums and the Lucene
version in its manifest. Importing it takes seconds: the files are checked, the directory is
moved into place (copied from another file system) and published. This needs the Lucene of
the same Isabelle release.

`-F interchange` exports the [interchange format](INTERCHANGE.md) instead: records and
vectors, independent of Lucene. Importing it indexes everything anew (about 30 minutes for the
whole AFP). Builds and interchange imports merge each corpus into one Lucene segment, so that
a search walks one HNSW graph.

`isasearch_index_build -i NAME -D DIR` packs an index into an Isabelle data component
`DIR/isasearch_NAME-DATE` (a `File_Store` database), which users register with
`isabelle components -u` and which is extracted on first use. A `File_Store` entry holds at
most 2 GB, so this does not work for the whole AFP.

## Search configuration

Without `-c FILE`, the searching tools (`isasearch_search`, `isasearch_server`,
`isasearch_duplicates`, `isasearch_benchmark`) read the configuration of the Isabelle option
`isasearch_config`, by default [`etc/search.json`](etc/search.json). It searches the released
index locally, with llama.cpp and the Q8_0 quantization of `Qwen3-Embedding-4B`, and no
generative model. To change it, copy the file and set the option in
`$ISABELLE_HOME_USER/etc/preferences`, e.g. `isasearch_config = "~/isasearch.json"`. Index
builds always need `-c`.

Relative paths in a configuration are resolved against its file; paths use Isabelle syntax
(`~` and variables are expanded). Prompts default to `prompts/qwen3-gemma`
(`prompts_folder`).

### Local model servers

With an object `llamacpp_embedding_server` or `llamacpp_query_server`, the searching tools
start llama.cpp's `llama-server` on 127.0.0.1 when the model is first needed and stop it when
they exit. The embedding server starts with the first search, the query server with the first
expanded query. llama.cpp downloads the model on first use and runs on a GPU (Metal, CUDA,
Vulkan) if its build supports one, otherwise on the CPU. Logs go to
`$ISASEARCH_HOME_USER/logs/llama-server-ROLE-TIME.log`. Index builds never start servers.

The embedding server replaces `openai_embedding_base_url` and answers as
`openai_embedding_model`; the query server replaces `openai_base_url`, answers as
`openai_query_model` and needs `llm_backend: "openai"`. Configuring both an object and the
endpoint it replaces, or an API key of that endpoint, is an error.

```json
"openai_embedding_model": "Qwen3-Embedding-4B",
"llamacpp_embedding_server": {"hf_repo": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0", "pooling": "last"},
"llm_backend": "openai",
"openai_query_model": "gemma-4-26B-A4B-it-qat",
"llamacpp_query_server": {"enabled": false, "hf_repo": "unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL"}
```

The default query server is the model that expands queries on the build server (Gemma 4
26B-A4B, QAT, `UD-Q4_K_XL`), disabled. With `"enabled": true` the first expanded query
downloads it (14 GB); an expansion then takes about 4 s on an M2 Pro, with about 5.4 GB
resident.

| Key | Meaning |
| --- | --- |
| `enabled` | `false` keeps the object without starting a server (default `true`) |
| `hf_repo` | Hugging Face model `user/repo:quant`, downloaded into llama.cpp's cache |
| `model_file` | a local GGUF file instead (Isabelle path syntax) |
| `pooling` | embedding only, e.g. `last` for Qwen3-Embedding (default: from the GGUF) |
| `context` | context in tokens, one slot (default 4096) |
| `port` | port on 127.0.0.1 (default: a free one) |
| `executable` | the server program (default `llama-server`) |
| `arguments` | further arguments, e.g. `["-ngl", "0"]` for CPU only |
| `startup_timeout` | seconds until ready, including a first download (default 1800) |

### Remote endpoints

For other setups, start from [`etc/config.example.json`](etc/config.example.json).
`llm_backend` (generation) and `embedding_backend` are set independently; `llm_backend: "none"`
searches without a generative model.

| Backend | Generation | Embeddings |
| --- | --- | --- |
| `openai` | `openai_base_url`, `openai_document_model`, `openai_query_model` | `openai_embedding_base_url`, `openai_embedding_model` |
| `ollama` | `ollama_base_url`, `ollama_document_model`, `ollama_query_model` | `ollama_base_url`, `openai_embedding_model` or `embedding_model` |
| `llamacpp` | `llamacpp_base_url`, optional `llamacpp_document_base_url`, `llamacpp_document_model`, `llamacpp_query_model` | an OpenAI-compatible endpoint |

Generation uses `sampling_parameters`; provider extensions go in `openai_extra_body`,
`ollama_options`, `llamacpp_extra_body` and `embedding_extra_body`.

Every endpoint `NAME_base_url` has an API key of its own, sent to that endpoint only: the
private file `NAME_api_key_file` (`chmod 600`), which takes precedence, or the environment
variable `NAME_api_key_env`. So `openai_api_key_file` is the key of `openai_base_url`, and
`openai_embedding_base_url` needs `openai_embedding_api_key_file`, also for the same server
and key. Keys never enter indexes.

The embedder must match the index: same model, pooling, normalization and truncation, and an
endpoint alias equal to the model name in the index manifest. Before searching, the tools embed
the reference inputs of the index again (a few short queries recorded by the build; for older
indexes, two documents per corpus) and fail if the vectors differ by more than
`embedding_reference_tolerance` (relative squared error, default 0.001).

Other limits and their defaults: `llm_request_timeout` (600 s), `inference_connect_timeout` and
`inference_health_timeout` (10 s), `llm_attempts` and `embedding_attempts` (3),
`openai_embedding_batch_size` (32), `openai_embedding_max_characters` (8000 for new indexes),
`capability_refresh_seconds` (30) and `search_candidates` (500: approximate neighbours ranked by
exact distance before the limit applies, because the HNSW graph alone misses some). HTTP 429
and transient errors are retried with backoff.

## Website and HTTP API

`isabelle isasearch_server [-p PORT]` serves the search page at its root
(<http://localhost:5001> by default) and the API below. It binds to loopback and answers only
requests whose `Host` is this machine (`localhost`, `127.0.0.1`, `[::1]`), so that pages of
other sites cannot use it; other requests get 403. For remote access, put an authenticated
reverse proxy in front and name the host it passes on in the option `isasearch_hosts` (comma
separated), e.g. `-o isasearch_hosts=search.example.org`. Requests are handled concurrently.
The page's libraries are vendored in `web/vendor`, so it works offline. Its controls follow
`/capabilities`.

- `GET /capabilities`: `generation`, `corpora`, `definition_search`, `embedding_available`,
  `embedding_error`, `query_expansion`, `query_expansion_error`, and `editors`.
- `GET /search?query=...&kind=theorems&refine_query=false`: `results`, `duration`,
  `refined_query`, `elapsed_duration` and `cache_hit`. `kind` is `theorems` or `definitions`.
  `refine_query=true` searches with the original and the expanded query together; it fails
  with 503 if query expansion is unavailable. Optional filters:
  - `source=distribution|afp|all` and `entries=E1,E2` select documents before the search, so
    the ranking within them is exact.
  - `sessions=S1,S2` and `mentions=T1 T2` keep documents of these sessions whose statement
    mentions every token: an identifier as a whole name component (`countable` matches
    `Set.countable`, not `uncountable`), anything else as text (`⋃`, `\<Union>`). They apply to
    the nearest `search_candidates` documents, so rare matches may return fewer results.
  - `collapse=true` merges hits with the same statement (e.g. AFP copies of HOL theories)
    into one result, represented by a distribution copy if there is one; the others follow
    under `copies`.
- `GET /source?kind=...&id=...`: the local file of a result, with line numbers and the source
  marked.
- `POST /open?editor=jedit|vscode&kind=...&id=...` (header `X-IsaSearch`): opens the local file
  at the result's line in Isabelle/jEdit or Isabelle/VSCode on the server's machine. The option
  `isasearch_editors` (default `jedit,vscode`) enables the editors; a public server sets it to
  `""`. A running Isabelle/VSCode is reused; a running Isabelle/jEdit only if it has an edit
  server, which the application bundles enable and a source checkout enables with
  `JEDIT_JAVA_SYSTEM_OPTIONS="$JEDIT_JAVA_SYSTEM_OPTIONS -Disabelle.jedit_server=NAME"` in
  `$ISABELLE_HOME_USER/etc/settings`.

Results link online (`remote_url` and `entry_url` for the AFP, `theory_url` for the Isabelle
library) and locally: `local_file` and `local_line` where `$AFP` or `$ISABELLE_HOME` is set and
the file exists below it; an index cannot name other files of the machine. The local file may
be a different version; `local_line` is the occurrence of the source nearest to the indexed
line, and missing if the file no longer contains it. Invalid parameters return 400.

## Building indexes

Building needs a registered AFP, a document LLM and an embedder.

```sh
isabelle isasearch_index -c build.json -i plain Example-Submission
isabelle isasearch_index -c build.json -i plain -c metadata.json -i metadata Example-Submission
```

One call builds several indexes, one per pair `-c FILE -i NAME`; indexes with the same
session settings share one Isabelle build and FindFacts index. Progress (documents done,
reused and new descriptions, rate, time left) also goes to
`$ISASEARCH_HOME_USER/logs/index-TIME-NAMES.log`. The run
[`runs/isabelle2026-gemma4`](runs/isabelle2026-gemma4/README.md) is a complete example.

The pipeline builds the sessions, extracts blocks through FindFacts, lets the LLM describe the
selected sources, and embeds description plus source.

### Configuration

- Sessions: arguments, or `isabelle_sessions`: `all-AFP`, or `all` for the AFP and the HOL
  sessions of the distribution without the documentation group. `isabelle_excluded_sessions`
  removes sessions.
- Isabelle build: `isabelle_build_jobs` (default 1), `isabelle_timeout_scale`, and
  `isabelle_session_options`, option updates per session in the syntax of `isabelle build -o`.
  For the whole AFP, `isabelle_timeout_scale: 3` keeps slow sessions in time, but
  `HOL-Metis_Examples` then needs `{"HOL-Metis_Examples": ["timeout_scale=1"]}`, because its
  SMT certificates are keyed by the solver timeout. `-n` skips building and indexes only
  sessions whose build is current.
- Metadata: `add_metadata` true or false; metadata builds use `PROMPTS-with-metadata`.
- Commands: `solr_query` and `solr_query_definitions` (defaults in `etc/corpus_defaults.json`).
- Concurrency: `llm_concurrency`; each batch of `openai_embedding_batch_size` documents is
  described concurrently and embedded in one request.

For the whole AFP, raise the JVM limits in `$ISABELLE_HOME_USER/etc/settings`:

```sh
ISABELLE_TOOL_JAVA_OPTIONS="-Djava.awt.headless=true -Xms2g -Xmx24g -Xss128m"
```

### Failures and resuming

- A session that fails to build is left out and reported; the manifest lists the sessions
  under `provenance.sessions` and `provenance.unbuilt_sessions`.
- Isabelle2026 occasionally builds a session without its PIDE exports, so FindFacts skips its
  theories ([details](../misc/isabelle-pide-exports-race.md)). Builds detect this and rebuild
  such sessions, up to three builds in all; a session that still lacks them is left out as
  `missing PIDE exports`.
- A description that fails after its retries is left out and generated by the next build; one
  cut off at `max_tokens` on every attempt is kept. The manifest lists them under
  `undescribed_documents` and `truncated_descriptions`.
- Pruning more than half of a corpus needs `allow_large_prune: true`.

Two stores, shared by all indexes, keep the work: `llm_cache` (descriptions, keyed by model and
exact request) and `embeddings` (keyed by backend, model, `embedding_extra_body` and input). A
stopped or reconfigured build therefore resumes: changed concurrency, endpoints or sessions
reuse everything, and a changed prompt, model or sampling parameter regenerates exactly the
affected documents. Nothing is deleted from the stores automatically.

All builds of a user share one FindFacts database (`isasearch`), re-indexed only when the
sessions or their builds change. Generated data lives under `$ISASEARCH_HOME_USER`, apart from
the session databases and the FindFacts database in their usual Isabelle locations.

### Provenance

The manifest records the Isabelle and AFP versions and revisions under `provenance`; benchmark
and duplicate reports copy it as `index_provenance`. For a traceable index, build from a clean
Mercurial clone at a fixed revision:

```sh
hg clone -u Isabelle2026 https://foss.heptapod.net/isa-afp/afp-2026 afp-2026
```

Builds warn if the AFP revision is unknown (e.g. an unpacked tarball) or the working directory
has local changes (`+` in the revision).

## Duplicate analysis

```sh
isabelle isasearch_duplicates -c config.json -i plain -k all -x -e Example-Submission
isabelle isasearch_duplicates -c config.json -i plain -k definitions -N 10 -J
```

`-e ENTRY` (repeatable) selects entries, `-N COUNT` the newest ones (default 10); `-k` selects
the corpora (default definitions), `-x` matches across kinds, `-J` disables the LLM judge, and
`-a` keeps all candidates in the JSON. Matches within the same entry are excluded. Without a
query LLM, reports contain only vector and syntactic evidence.

Thresholds and their defaults: `dedup_top_k` 10, `dedup_distance_threshold` 0.3,
`dedup_strong_distance_threshold` 0.05, `dedup_syntactic_threshold` 0.9,
`dedup_max_judged_per_item` 3. Distances depend on the index's metric.

Reports go to `$ISASEARCH_HOME_USER/reports` or `-D DIR`: a JSON file with all evidence, a
`_possible.md` view of the flagged candidates, a `_near-exact.md` view with source excerpts,
and a `_summary.md` table per entry. Entries of `-e` that are not in the index, e.g. because
their sessions failed to build, are listed as `missing_entries`.
Failed judge requests are retried, then recorded as `judge_error` and never cached. A
judgement cut off at `max_tokens` counts if its verdict is complete, and is marked
`judge_truncated`. More than 5% failed self-retrieval checks make the tool fail after saving
the evidence.

## Benchmarks

```sh
isabelle isasearch_benchmark -c config.json -i plain -m metadata -s all
isabelle isasearch_compare isabelle/benchmark/results/UR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json \
  /path/to/results/benchmark-UUID/UR
```

Strategies: `baseline` (original query), `R` (expanded), `UR` (both), and the metadata variants
`M`, `MR`, `MUR` (`-m` names the metadata index). The indexes must exist. The benchmark
(`benchmark/benchmark.csv`, or `-f FILE`) replays the paper's saved query inputs, including the
noisy queries, verified against the checksums in `benchmark/results/paper-baselines.json`;
new targets record `paper_noisy_query_missing`. It reports Hit@10, NDCG, reciprocal rank and
rank. Set `benchmark_add_top_results` for the top ten of each query.

Each run writes `benchmark-UUID/STRATEGY/results.json` and `manifest.json` (checksums, recipe,
provenance, sanitized configuration, timings). `isasearch_compare` takes result files or
strategy directories and recomputes the metrics on the queries both runs share. Durations
include replayed cached generation time (`cache_hit`); `enable_llm_output_cache: false` runs
the models uncached. See [benchmark/results](benchmark/results/README.md) for the paper's
baselines.

## Development

```sh
isabelle scala_build
isabelle isasearch_test
isabelle isasearch_integration_test
```

`isasearch_test` checks the algorithms against `tests/goldens.json`, reference outputs of the
original implementation (sequence ratios, paper queries, metrics, duplicate classification,
report views, comparisons). Interchange directories given as arguments are also imported,
searched, packaged and corrupted.

`isasearch_integration_test` runs the tools in isolated Isabelle user directories against a
local inference stub: imports, released indexes, all inference backends with failures, the HTTP
API and website, started model servers (fake `llama-server`s), exports, benchmarks and
duplicate analysis. With a registered AFP it also builds, updates and prunes indexes from
`Example-Submission`. No real model is contacted.

Sources follow the layout of Isabelle and FindFacts ([style guide](STYLE.md)). Application
choices are enums in `src/domain.scala`, parsed and printed only at CLI, configuration and JSON
boundaries.
