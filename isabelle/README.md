# IsaSearch for Isabelle/Scala

An Isabelle2026 component for semantic search, corpus construction, duplicate
analysis and the paper's benchmarks. The Python implementation and browser UI
remain available in the parent project. This component exposes an HTTP API and
command-line tools. Scala runtime dependencies come exclusively from Isabelle,
including its bundled Solr/Lucene. It neither starts nor installs model servers.

## Register and compile

From the repository root, with Isabelle2026 on `PATH`:

```sh
isabelle components -u "$PWD/isabelle"
isabelle scala_build
isabelle isasearch_search -?
```

The component is self-contained. It holds the benchmark dataset
(`benchmark/benchmark.csv`), the paper's baseline results with their verified
index (`benchmark/results`), the prompts (`prompts`), the configurations of index
runs (`runs`, e.g. `runs/isabelle2026-gemma4`), and frozen reference
outputs for its tests (`tests/goldens.json`). Compilation uses `etc/build.props`;
registered Scala tools use a FindFacts-style launcher to include Isabelle's Solr
classpath. No sbt, Maven, Python, or extra JVM libraries are needed.

AFP registration is needed only for building new content. Register an AFP 2026
installation with `isabelle components -u /path/to/afp` (registering its `thys`
directory works as well). Discovery uses `AFP.BASE`, `AFP.main_dir`, and
Isabelle's session structure, not a hard-coded checkout path. AFP metadata is
read from the registered root using Isabelle's TOML reader. Searching an imported
index, benchmarking it, or analyzing duplicates does not need AFP installed.

For a corpus that can be traced to its sources, build from a clean Mercurial clone
of the release repository, updated to a fixed revision:

```sh
hg clone -u Isabelle2026 https://foss.heptapod.net/isa-afp/afp-2026 afp-2026
```

The index manifest records the Isabelle identifier and revision and the AFP version
and working-directory revision (`hg id`, marked `+` for local changes) under
`provenance`. Builds warn when the AFP revision is unknown, e.g. for an unpacked
release tarball, or when its working directory has local changes. Benchmark
manifests and duplicate reports copy this as `index_provenance`.

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
are resolved against that configuration file. Prompts default to the component's
`prompts/qwen3-gemma`; set `prompts_folder` to use another folder.

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

Instead of an environment variable, `openai_api_key_file` names a private file with
the key, e.g. `$ISASEARCH_HOME_USER/api_key` (`chmod 600`); it takes precedence over
`openai_api_key_env`. Configuration paths use Isabelle syntax: variables and `~` are
expanded. Omit both for a server that does not require authentication.
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

One call can build several indexes in order, each from a pair `-c FILE -i NAME`:

```sh
isabelle isasearch_index -c /path/to/build-config.json -i plain \
  -c /path/to/metadata-config.json -i metadata Example-Submission
```

Indexes whose configurations request the same Isabelle build (sessions,
`isabelle_timeout_scale`, `isabelle_session_options`, `isabelle_build_jobs`) share
it, and with it the FindFacts index. Each call also logs its progress to
`$ISASEARCH_HOME_USER/logs/index-TIME-NAMES.log`. While describing, every batch
reports the documents prepared out of all of its kind, the reused and generated
descriptions, the rate and the time left, followed by the first new description of
the batch (with `-v`, all of them).

Building requires a document LLM and embedder. Set `add_metadata` to false or true
in the respective configurations. `prompts_folder` names the base folder:
metadata builds append `-with-metadata` (for example, `qwen3-gemma` becomes
`qwen3-gemma-with-metadata`). Select explicit session arguments or
`isabelle_sessions`: `all-AFP` selects the AFP sessions, and `all` adds the HOL
sessions of the distribution, without its documentation group (`doc`).
`isabelle_excluded_sessions` removes sessions. `solr_query` and
`solr_query_definitions` override command selection; defaults are in
`etc/corpus_defaults.json`.

The pipeline builds Isabelle sessions, extracts blocks through FindFacts,
informalizes selected source, then embeds description plus source. Prompts come
from `prompts_folder`; document/query models are independent. Metadata variants
are fixed at build time. `isabelle_build_jobs` (default 1) sets how many sessions
build in parallel; `isabelle_timeout_scale` scales their timeouts.
`isabelle_session_options` maps session names to option updates in the syntax of
`isabelle build -o`, applied after the session's ROOT options. For a whole AFP
build, `isabelle_timeout_scale: 3` keeps slow sessions within their timeouts, but
it also scales the SMT solver timeout that keys the read-only certificates of
`HOL-Metis_Examples`, so that session needs
`"isabelle_session_options": {"HOL-Metis_Examples": ["timeout_scale=1"]}`. A session that
fails to build, or is cancelled after a failed ancestor, is reported and left out;
the others are indexed, and the manifest lists the sessions in `provenance` under
`sessions` and `unbuilt_sessions`. `-n` skips building: only sessions whose
build is already current are indexed.

Isabelle2026 occasionally builds a session without the PIDE exports of its theories
(a race between prover exit and session stop), and FindFacts then skips all its
theories ("No snapshot for theory"). A build checks every built session for these
exports and builds the incomplete ones again, which rebuilds their descendants, up
to three builds in all; a session that still lacks them, or lacks them under `-n`,
is left out as `missing PIDE exports`.

All builds of a user share one FindFacts database (`isasearch`). It is re-indexed
only when the indexed sessions or their builds change; otherwise a build reports
that the index is current and reuses it, so a metadata build after a plain build
of the same sessions does not index again. Each build exports the blocks it needs
under a lock, which a concurrent build waits for while the database is re-indexed,
and then works from its export.

All generated data lives beneath `$ISABELLE_HOME_USER/isasearch`, apart from the
standard session databases and the FindFacts database in their Isabelle-managed
locations. Build concurrency is bounded by `llm_concurrency`; each batch of
`openai_embedding_batch_size` documents is described concurrently and then
embedded in one request.

For the whole AFP, raise the JVM limits in `$ISABELLE_HOME_USER/etc/settings`, e.g.
`ISABELLE_TOOL_JAVA_OPTIONS="-Djava.awt.headless=true -Xms2g -Xmx24g -Xss128m"`:
indexing runs in the tool's JVM, the default heap does not suffice for the whole
Archive, and `Isabelle_C` overflows the default stack.

Progress is kept in two stores shared by all indexes, keyed only by what
determines their content:

- `llm_cache`: model outputs, keyed by the model and the exact request body
  (rendered prompt, sampling parameters, provider extensions), not by endpoint.
  Corpus builds always store descriptions, independently of
  `enable_llm_output_cache`, which only governs queries and the duplicate judge.
- `embeddings`: float32 vectors, keyed by backend, model, `embedding_extra_body`,
  and the exact (truncated) input.

Document records are rebuilt from the current FindFacts blocks on every run, so
positions, links, and metadata always describe the indexed sources. An interrupted
or reconfigured build therefore resumes with everything already described and
embedded: changing concurrency, timeouts, endpoints, or session selection reuses
the stores, while a changed prompt, model, or sampling parameter regenerates exactly
the documents whose request changes. Plain and metadata indexes can be built at the
same time. A per-index lock prevents competing builds of one index. Index
generations publish atomically; existing readers retain their opened generation.
Old generations and store entries are never deleted automatically; remove them
manually once no readers or builds need them.

### Seed descriptions from Python artifacts

Descriptions that the Python implementation generated can seed the store, so that a
build does not describe those documents again:

```sh
isabelle isasearch_seed -c /path/to/build-config.json \
  artifacts/MODEL/document_descriptions.json artifacts/MODEL/definition_descriptions.json
```

Use the build configuration: each stored description is keyed by the request this
configuration sends for the artifact's recorded prompt, so a build reuses it exactly
when it renders the same prompt for the same document model. Entries of another or
unrecorded model, and entries without prompt or marked description, are skipped
and counted. Existing store entries are kept. The configuration must describe how the
artifacts were generated (sampling parameters and provider extensions); this cannot
be checked from the artifacts. Python kept descriptions that were cut off at
`max_tokens`, which builds would reject; seeded entries are accepted as stored.
Artifacts are streamed and read without Python. After seeding, they are no longer
needed; each build reports how many stored descriptions it reused.

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
`-x` for cross-kind matching, `-J` to disable judging, and `-a` to retain every
candidate in JSON. Markdown always omits unclassified neighbours. Default
selection is definitions. Cross-kind matching requires
compatible embedding contracts. Same-entry results are excluded; self-retrieval
checks and syntactic evidence are reported independently. Without a usable query
LLM, reports contain vector/syntactic evidence only.

Defaults match Python: `dedup_top_k=10`, `dedup_distance_threshold=0.3`,
`dedup_strong_distance_threshold=0.05`, `dedup_syntactic_threshold=0.9`, and
`dedup_max_judged_per_item=3`. Reports are saved under the user reports directory
or `-D`: one JSON file containing the evidence, a `_possible.md` view of all
flagged candidates, and a `_near-exact.md` view with candidate source excerpts.
Both views include source links and escape document names and model text.
Failed judge requests are retried; exhausted failures remain unjudged, carry
`judge_error`, and are counted in `judge_failures`. They are never cached, so a
later run retries them. Other candidate pairs still finish. A self-retrieval
failure rate above 5% exits unsuccessfully after saving the evidence.
Distances are metric-specific; thresholds must be interpreted with the selected
index's metric.

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
Historical targets replay all three saved paper inputs verbatim, including the
noisy query, verified against the UR checksum in `paper-baselines.json`. This
matches Python's `benchmark.queries`; it does not generate new noise. Additional
targets use the CSV title and natural-language queries and record
`paper_noisy_query_missing` for the noisy query. Current CSV target identifiers
are retained in result metadata. Set `benchmark_add_top_results` for top-ten details.

Every invocation creates a new `benchmark-UUID/STRATEGY/` directory per strategy,
with `results.json` and `manifest.json`. The manifest records index/dataset checksums,
recipe, index provenance, sanitized configuration, query-input provenance, timestamps,
cache policy, and actual query timings. Compare a run with a paper baseline or
another run on identical query texts:

```sh
isabelle isasearch_compare \
  isabelle/benchmark/results/UR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json \
  /path/to/results/benchmark-UUID/UR
```

Either argument is a result file or a strategy directory. The Markdown report
recomputes Hit@10, MRR, and NDCG on the queries both runs share with the same input
text and relevance labels, and lists the excluded and skipped queries and the
largest reciprocal-rank changes.
Legacy duration includes replayed cached generation time for comparison;
`elapsed_duration` records measured execution and `cache_hit` identifies replay.
Set `enable_llm_output_cache=false` for uncached model execution.

## Development and validation

```sh
isabelle scala_build
isabelle isasearch_test
isabelle isasearch_integration_test
```

`isasearch_test` checks the portable algorithms against `tests/goldens.json`:
reference outputs of the former Python implementation for SequenceMatcher ratios,
replayed paper queries, metrics, duplicate classification, verdict parsing,
statement normalization, both duplicate report views, and benchmark comparisons.
Interchange directories given as arguments are imported, searched, packaged, and
corrupted.

`isasearch_integration_test` runs the command-line tools in isolated Isabelle user
directories against a deterministic local inference stub: interchange import,
search over all inference backends with retries and failures, the HTTP API,
packaged indexes, query caching, benchmarks, and duplicate analysis with judge
failures. With a registered AFP it also builds, seeds, updates, and prunes corpora
from `Example-Submission`. No real model is contacted.

Application choices use enums in `src/domain.scala`; parsing and serialization
happen at CLI, configuration, and JSON boundaries. Protocol field names remain
strings. Isabelle supplies JSON, TOML, options, session discovery, HTTP serving,
Solr (including its multiline CSV reader), and File_Store. Compatibility
algorithms absent from the bundled API (SequenceMatcher) are local. Saved query
inputs, scoring, both report views, and comparisons are covered by the goldens.
Scala sources follow the
manual layout of Isabelle and FindFacts; see [the style guide](STYLE.md).
