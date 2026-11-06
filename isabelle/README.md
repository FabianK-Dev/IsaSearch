# IsaSearch for Isabelle/Scala

An Isabelle2026 component for semantic search, corpus construction, duplicate
analysis and the paper's benchmarks. It exposes the search website, an HTTP API and
command-line tools. Scala runtime dependencies come exclusively from Isabelle,
including its bundled Solr/Lucene. It installs no model servers; on request, the searching
tools start an installed llama.cpp server for query embeddings.

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
the `isasearch_*` tools in `lib/Tools` run, as the FindFacts tools do, in a JVM of
their own with Isabelle's Solr classpath (`lib/scripts/isasearch`). No sbt, Maven, or
extra JVM libraries are needed.

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

## Index generations

Builds write their corpora in the [interchange format](INTERCHANGE.md) and publish
them through the import that `isabelle isasearch_import -f DIR -i NAME` offers for
any interchange directory; the same command installs an exported generation as it is
(see "Distribute indexes"). Imports validate into a new generation and publish only
after all corpora succeed. Failed imports preserve the previous generation. Before
publishing, every corpus is merged into a single Lucene segment, so that a search
walks one HNSW graph rather than one per imported batch; a generation published
without this merge stays slow until it is imported or built again. Reported cosine
distance and squared Euclidean distance are computed from the retained vectors,
independently of Lucene's scores.

Indexes live by name in `$ISASEARCH_HOME_USER/indexes/NAME`. The tools select one with
`-i NAME`; without it they use the Isabelle option `isasearch_index`, by default `plain`, the
name under which the released index is imported.

## Configure inference and search

Without `-c`, the searching tools (`isasearch_search`, `isasearch_server`,
`isasearch_duplicates`, `isasearch_benchmark`) read the configuration named by the
Isabelle option `isasearch_config`. It defaults to the component's `etc/search.json`, which
searches the released index on the local machine: it starts llama.cpp with the Q8_0
quantization of `Qwen3-Embedding-4B` (see "Local embedding server") and uses no generative
model. To change it, copy the file, edit the copy, and point the option at it in
`$ISABELLE_HOME_USER/etc/preferences`, e.g. `isasearch_config = "~/isasearch.json"`; an
empty value means no default. `-c FILE` replaces the default for one call. Index builds
take no default and need `-c`.

For other setups, copy `etc/config.example.json` and adjust URLs and model names. Relative
paths are resolved against that configuration file. Prompts default to the component's
`prompts/qwen3-gemma`; set `prompts_folder` to use another folder.

For search without a generative LLM, leave `llm_backend` as `none`. An embedding
service is still required. A user-managed CPU embedding server can expose an
OpenAI-compatible `/v1/embeddings` endpoint; configure its base URL and give it
the same model identity, tokenizer, pooling, normalization, and truncation as
the index. Endpoint aliases must match the model name recorded in the manifest.
The client validates dimensions and re-embeds reference inputs before querying: the
reference embeddings that the build recorded (a few short queries), or two documents
of each corpus for indexes built without them. A mismatch is an error rather than
silently returning invalid similarities.

```sh
isabelle isasearch_search 'a finite union of countable sets'
export ISASEARCH_API_KEY='your-server-key'
isabelle isasearch_search -c /path/to/config.json -i plain 'a finite union of countable sets'
isabelle isasearch_search -c /path/to/config.json -i plain -k definitions 'a partial order'
isabelle isasearch_server -c /path/to/config.json -i plain -p 5001
```

### Local model servers

Searches can start their models themselves instead of using running endpoints. With an
object `llamacpp_embedding_server` or `llamacpp_query_server` in the configuration,
`isasearch_search`, `isasearch_server`, `isasearch_duplicates` and `isasearch_benchmark`
start `llama-server` from llama.cpp on 127.0.0.1 when the model is first needed, wait until
its `/health` reports ready, send the requests of its role there and stop it when they exit.
The embedding server starts with the first search (or check of the embedder), the query
server with the first expanded query, so a configured but unused expansion costs nothing.
Their output goes to `$ISASEARCH_HOME_USER/logs/llama-server-ROLE-TIME.log`. llama.cpp must
be installed (e.g. `brew install llama.cpp`, or a release binary from its GitHub page);
llama.cpp offloads to a GPU (Metal, CUDA, Vulkan) when its build supports one and computes on
the CPU otherwise. Index builds do not start servers.

Both servers behave as the endpoints they replace, so a configuration for local models
differs from one for remote servers only in these objects: the embedding server answers
under `openai_embedding_model` and replaces `openai_embedding_base_url`, the query server
answers under `openai_query_model`, replaces `openai_base_url` and needs `llm_backend`
`openai`. Prompts, `openai_extra_body` and `sampling_parameters` apply unchanged.
Configuring an object and the endpoint it replaces is an error; `"enabled": false` keeps an
object without using it.

The default `etc/search.json` runs the embedder of the released index and carries the query
model of the server that builds it, Gemma 4 26B-A4B (the QAT model at `UD-Q4_K_XL`, as served
there), with the server's sampling parameters, disabled:

```json
"openai_embedding_model": "Qwen3-Embedding-4B",
"llamacpp_embedding_server": {
  "hf_repo": "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0",
  "pooling": "last"
},
"llm_backend": "openai",
"openai_query_model": "gemma-4-26B-A4B-it-qat",
"llamacpp_query_server": {
  "enabled": false,
  "hf_repo": "unsloth/gemma-4-26B-A4B-it-qat-GGUF:UD-Q4_K_XL"
}
```

Setting `enabled` to `true` (in a copy of the file, see above) turns on query expansion: the
first expanded query downloads the model (14 GB) and starts it; on an M2 Pro an expansion
takes about 4 s, and the running model kept about 5.4 GB resident (see
`runs/isabelle2026-gemma4/README.md`). Without the object, or with it disabled, query
expansion is not configured and searches never expand.

| Key | Meaning |
| --- | --- |
| `enabled` | `false` keeps the object without starting a server (default `true`) |
| `hf_repo` | Hugging Face model `user/repo:quant`; llama.cpp downloads it into its cache on first use |
| `model_file` | a local GGUF file instead (Isabelle path syntax) |
| `pooling` | embedding only: pooling of the model, e.g. `last` for Qwen3-Embedding; default: from the GGUF |
| `context` | context in tokens, one slot (default 4096) |
| `port` | port on 127.0.0.1 (default: a free one) |
| `executable` | the server program (default `llama-server`) |
| `arguments` | further llama-server arguments, e.g. `["-ngl", "0"]` for CPU only |
| `startup_timeout` | seconds until ready, including a first download (default 1800) |

The query server is started without a multimodal projector (`--no-mmproj`), which llama.cpp
would otherwise download with an `hf_repo`.

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
embedding inputs. It never downloads a model.

Common limits have configuration owners: `llm_request_timeout` (600 seconds),
`inference_connect_timeout` (10), `inference_health_timeout` (10), `llm_attempts`
and `embedding_attempts` (3), `openai_embedding_batch_size` (32),
`openai_embedding_max_characters` (8000 for newly built indexes), and
`capability_refresh_seconds` (30). Imported indexes retain their own truncation
contract. `embedding_reference_tolerance` defaults to 0.001 relative squared
error. Searches and duplicate lookups rank `search_candidates` (500) approximate
nearest neighbours by exact distance before applying their limit, because the
HNSW graph alone misses some of the nearest documents. HTTP 429 and transient server/transport errors are retried with bounded
backoff. Failed, empty, or truncated completions are not cached, with one
exception: a corpus description that is cut off at
`max_tokens` on every attempt is kept, stored as truncated, and reported. A document
whose description still fails after its retries is left out of the index, reported,
and described by the next build; a batch in which no description succeeds stops the
build. Corpus entries of the manifest list these documents under
`truncated_descriptions` and `undescribed_documents`.

## Website

`isabelle isasearch_server` also serves the search page at its root, e.g.
`http://localhost:5001/` for `-p 5001`. The page and its libraries live in `web`
and the libraries are vendored in
`web/vendor`, so the page works without network access. Controls follow
`/capabilities`: definition search appears with a definitions corpus, query
refinement is disabled while query expansion is unavailable, and an unavailable
embedding service is reported above the search form. Theory, entry and file
links appear where results have them.

## HTTP API

- `GET /capabilities` returns `generation` (the generation served), `corpora`,
  `definition_search`, `embedding_available`, `embedding_error`, `query_expansion`,
  `query_expansion_error`, and `editors` (name and title of each enabled editor).
- `GET /search?query=...&kind=theorems&refine_query=false` returns `results`,
  `duration`, `refined_query`, plus `elapsed_duration` and `cache_hit`.
  Results retain source fields, descriptions, links, and distances. Exact
  embedding inputs and internal description artifacts are not exposed.
  Optional parameters narrow and condense the results:
  - `source=distribution` or `source=afp` (default `all`) and `entries=E1,E2` (only these AFP
    entries, besides the distribution unless `source=afp`) select documents before the
    nearest-neighbour search, so the ranking is exact within them.
  - `sessions=S1,S2` and `mentions=T1 T2` keep the documents of these sessions whose statement
    mentions every token: an identifier as a whole component of a name (`countable` matches
    `Set.countable`, not `uncountable`), anything else such as `⋃` or `\<Union>` as text. They
    apply to the nearest `search_candidates` documents of the selection (500 by default), so a
    rare match may yield fewer results than `limit`.
  - `collapse=true` returns the hits with the same statement (proof, command, name and
    attributes aside), e.g. the copies of HOL theories in the AFP entry Zippy, as one result,
    ranked by its nearest copy and represented by a copy from the distribution if there is
    one; the others follow under `copies`.
- Results link to their sources online (`remote_url` and `entry_url` for the AFP,
  `theory_url` for the Isabelle library) and on this machine: where the variable of
  their `file` is set (`AFP` for a registered AFP, `ISABELLE_HOME`) and the file exists,
  `local_file` is its path and `local_line` the line of the document's source in it.
  The local file may be another version than the indexed one: `local_line` is the
  occurrence of the source nearest to `start_line`, and missing if the file no longer
  contains it. The website links both; its local link opens
  `GET /source?kind=...&id=...`, the local file with line numbers and the source marked.
- `POST /open?editor=...&kind=...&id=...` with the header `X-IsaSearch` opens the local
  file of a document at its line in an Isabelle editor on the server's machine:
  `jedit` (Isabelle/jEdit) or `vscode` (Isabelle/VSCode). It is served for the editors
  that the Isabelle option `isasearch_editors` enables (comma separated, by default
  `jedit,vscode`), and the website shows an "Open in Isabelle/jEdit" and an "Open in
  Isabelle/VSCode" link for each local file. A server for other machines, behind a
  reverse proxy, sets `isasearch_editors = ""`: it must not start editors where it runs. A running
  Isabelle/VSCode is reused; a running Isabelle/jEdit only if it has an edit server, which
  Isabelle's application bundles enable and a source checkout enables with
  `JEDIT_JAVA_SYSTEM_OPTIONS="$JEDIT_JAVA_SYSTEM_OPTIONS -Disabelle.jedit_server=NAME"`
  in `$ISABELLE_HOME_USER/etc/settings`; otherwise each request starts a new jEdit. The
  header keeps pages of other origins from sending the request.
- `kind` is `theorems` or `definitions`. Query expansion defaults to off. Enabling
  it concatenates the original and expanded queries. An explicit request fails
  with HTTP 503 if the configured query LLM is unavailable; it never silently
  runs a different strategy. Invalid parameters return 400.

Capability state is refreshed periodically and updated after inference failures.
Model availability is checked through real inference, not just the existence of
a configured URL; a local query server that has not started yet counts as available.
Search and API startup never build a corpus.

The server follows its index: every request reads `current.json` and opens a newly
published generation, from a build or an import, so a server never needs a restart for
new data. The previous generation is closed when its last request ends; a generation that
fails to open is reported and leaves the previous one in service.

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
Old generations and store entries are never deleted automatically; remove
generations with `isasearch_prune` and store entries by hand once no readers or
builds need them.

Pruning more than half of a previously indexed corpus requires the explicit
configuration `allow_large_prune: true`. Review session selection first. Empty
corpora are omitted; an entirely empty index is rejected.

## Distribute indexes

```sh
isabelle isasearch_index_build -i plain -D /path/to/components
isabelle components -u /path/to/components/isasearch_plain-YYYYMMDD
```

The tool creates an Isabelle data component with a compressed `File_Store`
database and settings. Ship this directory alongside the code component. For a
bundled index, place the generated `plain.db` under the code component's
`lib/indexes/`. Users select it with `-i plain`. Distribution archives are
immutable: first use extracts into the writable user directory, then opens
read-only Lucene readers. No generative model is needed to extract or use a
prebuilt corpus. Configuration and inference caches are not packaged. A `File_Store`
entry holds at most 2 GB, so this does not work for the whole AFP, whose vector
files are larger.

```sh
isabelle isasearch_export -i plain -D /path/to/directory
isabelle isasearch_import -f /path/to/directory/isasearch-plain -i plain
```

`isasearch_export` writes the current generation of an index to a directory
`isasearch-NAME`, ready to search: copies of the generation's files as they are, with
their checksums and the Lucene version in its manifest (see
[INTERCHANGE.md](INTERCHANGE.md)). `isasearch_import` installs such a directory in
seconds: it checks the files, moves the directory into place (copies it from another
file system), opens it and publishes it. It needs the Lucene of the same Isabelle
release.

`-F interchange` writes the interchange format instead: the stored records and
their original vectors in document order, and the manifest of the generation with
new file checksums. It does not depend on the bundled Lucene version, and
`isasearch_import` indexes it anew on any machine, which takes half an hour for the
whole AFP. The run `runs/isabelle2026-gemma4` publishes exported generations as
GitHub releases; see its README.

`isasearch_prune -i NAME` removes the generations of an index other than its
current one. A server that still has an old generation open keeps reading it
until its last request on it ends.

## Duplicate analysis

```sh
isabelle isasearch_duplicates -c /path/to/config.json -i plain -k all -x -e Example-Submission
isabelle isasearch_duplicates -c /path/to/config.json -i plain -k definitions -N 10 -J
```

Use repeated `-e` for explicit entries, `-N` for newest entries by indexed dates,
`-x` for cross-kind matching, `-J` to disable judging, and `-a` to retain every
candidate in JSON. Markdown always omits unclassified neighbours. Default
selection is definitions. Cross-kind matching requires
compatible embedding contracts. Same-entry results are excluded; self-retrieval
checks and syntactic evidence are reported independently. Without a usable query
LLM, reports contain vector/syntactic evidence only.

Defaults: `dedup_top_k=10`, `dedup_distance_threshold=0.3`,
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
and no corpus caches are deleted.

The runner handles multiline CSV and JSON targets, skip annotations, missing
targets, title/natural/noisy queries, and the paper's Hit@10, NDCG, reciprocal rank,
rank, and sample counts. It preserves the existing JSON structure and labels.
Historical targets replay all three saved paper inputs verbatim, including the
noisy query, verified against the UR checksum in `paper-baselines.json`. It does
not generate new noise. Additional
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
frozen reference outputs of the original implementation for SequenceMatcher ratios,
replayed paper queries, metrics, duplicate classification, verdict parsing,
statement normalization, both duplicate report views, and benchmark comparisons.
Interchange directories given as arguments are imported, searched, packaged, and
corrupted.

`isasearch_integration_test` runs the command-line tools in isolated Isabelle user
directories against a deterministic local inference stub: interchange import,
reference embeddings, search over all inference backends with retries and failures,
the HTTP API and the website with its assets, a server following a newly published
generation, started embedding and query servers (with fake `llama-server`s), exported
generations and their installation, packaged indexes, query caching, benchmarks, and
duplicate analysis with judge failures. With a registered AFP it also builds, updates, and prunes corpora
from `Example-Submission`. No real model is contacted.

Application choices use enums in `src/domain.scala`; parsing and serialization
happen at CLI, configuration, and JSON boundaries. Protocol field names remain
strings. Isabelle supplies JSON, TOML, options, session discovery, HTTP serving,
Solr (including its multiline CSV reader), and File_Store. Compatibility
algorithms absent from the bundled API (SequenceMatcher) are local. Saved query
inputs, scoring, both report views, and comparisons are covered by the goldens.
Scala sources follow the
manual layout of Isabelle and FindFacts; see [the style guide](STYLE.md).
