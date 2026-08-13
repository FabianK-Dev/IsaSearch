# IsaSearch

This repository provides an AI-assisted semantic theorem search for the Archive of Formal Proofs using sentence-transformers, ChromaDB and LLMs. Additionally, it contains our benchmark data and results.

## Requirements

- [Python](https://www.python.org/downloads/) 3.11.2 or higher
- [pip](https://pip.pypa.io/en/stable/installation/) 23.0.1 or higher
- [git](https://git-scm.com/downloads) 2.47.3 or higher
- [Docker](https://www.docker.com/get-started) 29.2.1 or higher
- `fontconfig` and at least one font family. Isabelle brings its own JDK, but that JVM initializes
  AWT while indexing and aborts with `*** Fontconfig head is null` on a machine that has no fonts at
  all — which a minimal server install typically does not. On Debian or Ubuntu:
  `sudo apt-get install -y fontconfig fonts-dejavu-core`
- One of the supported LLM backends:
  - an OpenAI-compatible server (what the checked-in `config.json` is configured for, see below), or
  - [Ollama](https://ollama.com/download), which the application starts itself, or
  - [llama.cpp](https://github.com/ggml-org/llama.cpp) with `llama-server` available on the `PATH`

## Setup

### Quickstart

> ⚠️ **Warning:** Please run the following commands **inside the root folder of the repository** (this is necessary to ensure files like `config.json` are loaded correctly):

```bash
python3 -m venv .venv  # If this command does not work, please install the `venv` module for Python: `pip install venv`
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m src.corpus  # builds everything the application serves, see below
python3 -m src.app
```

There are two commands because there are two roles, and the split is what lets the website and the duplicate detection run side by side:

- **`python3 -m src.corpus` builds.** It installs Isabelle and the AFP, builds the Isabelle FindFacts index, fetches the documents from Solr, has the LLM informalize each of them once and embeds the result into ChromaDB. It is the only process that writes, so it runs alone. It is resumable and skips everything that is already up to date, so re-running it after an AFP update only processes what changed.
- **`python3 -m src.app` and `python3 -m src.duplicates` read.** Both attach to what the build produced and never generate anything. A corpus that was not built is reported rather than built, so starting the website can never kick off a multi-hour informalization run.

> ⚠️ **Before the first command works, point it at an LLM.** The checked-in `config.json` sets `"llm_backend": "openai"` and `"embedding_backend": "openai"` against the servers of our group, which are on a private network, and it reads the key from `ISASEARCH_API_KEY`. Both backends are contacted at start-up, so an unreachable one fails immediately rather than at the first query. Either export the key and use URLs you can reach, or run everything locally by setting `"llm_backend": "ollama"` and `"embedding_backend": "sentence_transformers"` — then the application starts Ollama itself and pulls the configured models if they are missing, and the embeddings are computed in-process. (There is no `"ollama"` embedding backend.) See "LLM backend" and "Embedding backend" below.

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

`"openai_extra_body"` is merged verbatim into every request, for the settings a local server needs that the OpenAI API never standardised.

`"llm_concurrency"` is how many informalization requests are in flight at once. Informalizing is by far the longest step of a build, and an inference server that batches — every `llama-server` started with `--parallel` — is mostly idle while one blocking request is answered. Match it to what the server can actually take; llama.cpp reports that as `total_slots` at its `/props` endpoint. It defaults to 1, because a server that does not batch gains nothing and one that is also serving the website should not be saturated by a build.

> ⚠️ **Turn a reasoning model's thinking off.** A model that thinks before it answers returns its thinking in `reasoning_content` and the answer in `content`. On this task the thinking does not terminate: measured against `gemma-4-26B-A4B`, a one-line corollary produced 3000–4000 characters of reasoning, ran into `max_tokens` every single time, and returned `content: ""`. The corpus is then built out of empty descriptions, which embed fine and retrieve nothing. Switching it off made the same requests **10× faster** (1.8 s instead of 17.7 s) and correct:
>
> ```json
> "openai_extra_body": {"chat_template_kwargs": {"enable_thinking": false}}
> ```
>
> That is the flag llama.cpp hands to the chat template; the server side equivalent is `--reasoning-budget 0`. To find out whether a model has such a switch, read its `chat_template` from the server's `/props` endpoint and look for `enable_thinking`.
>
> Keep `"stop"` empty for the same reason. The prompts ask for the answer wrapped in `<BEGIN>` and `<END>`, and a reasoning model restates that instruction to itself while thinking, so `"stop": ["<END>"]` ends generation *inside* the reasoning block with the same empty result.
>
> Verify with `python3 -m unittest tests.test_server_availability -v` and by reading `artifacts/<model>/document_descriptions.json`, which stores the raw output and the exact prompt for every document. A build that produces empty descriptions warns about it, but only after the fact.

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

It works on the same Solr index as the theorem search. Isabelle's FindFacts indexes *every* command block of a theory, so the definitional commands were in the index all along; only `"solr_query"` filtered them out. The corpus build therefore produces a second corpus from `"solr_query_definitions"`, with its own document index cache (`.cache/definition_index.json`), its own LLM descriptions (`artifacts/<model>/definition_descriptions.json`) and its own ChromaDB collection (`afp_definitions`). The theorem corpus is never modified.

The analysis itself is read-only and cheap — it embeds nothing and only queries what is already there — so it can run while the website is up. Everything expensive happens once, in `python3 -m src.corpus`.

#### What one run does

For every document of the analysed entry, in this order:

1. The document is turned into the very same embedding string the corpus side used for it, so query and corpus live in one space.
2. It is queried against the ChromaDB collection, and the rank and distance at which it retrieves *itself* are recorded. That is a positive control needing no ground truth: a document must find itself at a distance of about 0.
3. All candidates belonging to the analysed entry are dropped — this is the "ignore the entry's own definitions" part.
4. Each remaining candidate gets a syntactic similarity score and, unless switched off, a verdict from the LLM. Distance, similarity and verdict together decide the tier it is reported in.

The result is `reports/duplicates/experiment_<timestamp>.md` for reading and `.json` for the raw numbers.

#### Case 1: an entry that is already in the corpus

This is the common case and takes minutes. Name the entry, or let it pick the newest ones:

```bash
python3 -m src.duplicates --entry Ramsey-Infinite --kinds all
```

```bash
python3 -m src.duplicates --newest 10
```

Useful options:

| Option | Effect |
| --- | --- |
| `--entry NAME` | analyse this entry instead of the newest ones, may be repeated |
| `--kinds all` | analyse definitions *and* theorems (`--kinds theorems` for theorems only) |
| `--cross` | match every document against *both* corpora, see below |
| `--no-llm-judge` | switch the LLM adjudication off, see below |
| `--all-candidates` | report the closest candidates of *every* document, not only those reaching a tier |
| `--report-dir DIR` | override the report location |

Only entries that are part of the corpus can be analysed. An entry that is not is skipped with a warning naming it, and `--newest` warns about newer entries it had to pass over because they are not indexed.

#### Case 2: a submission that is not in the AFP yet

A new submission has to be built into the corpus before it can be analysed — its documents have to be indexed, informalized and embedded like every other. That is a corpus build, so it is the expensive path:

1. **Put the submission into the AFP checkout.** The sources go to `afp/thys/<Entry>/` and the metadata to `afp/metadata/entries/<Entry>.toml`. The metadata file carries the submission date; `--entry` works without it, `--newest` needs it to rank the entry.
2. **Make the session part of the corpus.** If `"isabelle_sessions"` is not `["all"]`, add the entry's session name to it in `config.json`.
3. **Rebuild the corpus.** With Solr stopped, then started:

   ```bash
   python3 -m src.corpus --index-only
   python3 -m src.corpus
   ```

   Only the new documents are informalized and embedded, because descriptions and embeddings are keyed by a checksum of their source code. Changing the session list does make Isabelle index again, which is the slow part.
4. **Analyse it.**

   ```bash
   python3 -m src.duplicates --entry <Entry> --kinds all
   ```

Two things to watch out for while a submission under review sits in the working tree. `"check_for_updates": true` makes every build fetch the AFP and **reset the checkout to the remote**, so set it to `false` while you are reviewing. The submission itself survives that reset — it is untracked — but any edit you made to a tracked AFP file does not. And the entry has to build under the pinned Isabelle release — a submission written against a newer Isabelle will fail during indexing, not during the analysis.

In both cases the entry's own definitions and theorems are excluded from its own results, so what the report contains is counterparts *elsewhere* in the AFP, for you to compare by hand.

#### Cross-kind matching

By default definitions are matched against definitions and theorems against theorems. With `--cross` every analysed document is matched against both corpora at once, so a definition of the analysed entry can also surface a lemma elsewhere in the AFP that states the same thing, and vice versa:

```bash
python3 -m src.duplicates --newest 10 --cross
```

This is sound because both collections are filled by the same embedding function with the same `embed` prompt into the same cosine space, so their distances are directly comparable and the two result lists can be merged into one ranking. Each candidate in the report carries the Isabelle command it came from. The report sections stay keyed by the kind of the *analysed* documents, and the positive control is still taken from the corpus the analysed document itself lives in — otherwise a cross-kind near-twin could outrank the document itself and look like a broken index.

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

#### Searching definitions in the web UI

Once the definitions corpus exists, the web UI offers a **Search in: Theorems / Definitions** selector, and the `/search` endpoint takes a `kind` parameter (`theorems` by default, or `definitions`).

The application only ever *attaches* to the definitions corpus, it never builds it: starting the web server must not kick off a multi-hour informalization run. If the corpus is missing or empty, definition search is simply not offered — the selector stays hidden, `/capabilities` reports `{"definition_search": false}` and `/search?kind=definitions` answers with a 503 explaining how to build it. A partially built corpus is served without the definitions that have no description yet, so a server can keep running while the corpus is being rebuilt.

If `prompts/<folder>/retrieve_definitions.txt` and `search_refine_definitions.txt` exist, they are used for definition searches instead of the theorem-flavoured `retrieve.txt` and `search_refine.txt`; deleting them falls back to the theorem prompts. The theorem search and the benchmark are unaffected either way.

Please keep in mind that semantic similarity is not logical duplication: the tiers are a triage aid for a human reviewer, not a verdict. The same holds for the LLM verdicts, which is why the report always contains the model's justification. Also note that meaningful results require an index of the whole AFP — with only the two sessions that are enabled for testing, almost nothing can be found.

### Running on a server

On a deployed server the web application and the duplicate detection are meant to run at the same time, sharing one Solr index, one set of informalisations and one ChromaDB storage. That is safe as long as every artifact has exactly one writer, which is what the build/serve split enforces.

The deployment is one image in three roles, described by [compose.yaml](compose.yaml). The image contains the code and its Python dependencies and nothing else; everything mutable — the Isabelle and AFP checkouts, `~/.isabelle` with its contrib and the FindFacts Solr core, `.cache/`, `artifacts/`, `chroma_storages/` and `reports/` — lives on a single `state` volume mounted at `/data`. Solr runs as its own service so that both serving processes can reach it.

#### Preparing the server

Only Docker and a checkout of this repository are needed; Isabelle and the AFP install themselves into the volume on the first build.

1. Clone the repository and edit `config.json`:
   - `"solr_core_url": "http://solr:8983/solr/local"` — the compose service name, not `localhost`.
   - `"isabelle_sessions": ["all"]` once the dry run below has succeeded. Leave the two default sessions in place for the dry run.
   - Confirm that `openai_base_url` and `openai_embedding_base_url` are reachable from inside a container, not just from the host.
2. Put the API key into a `.env` file next to `compose.yaml`:

   ```
   ISASEARCH_API_KEY=...
   ```

3. Build the image:

   ```bash
   docker compose build
   ```

#### 1. Build the corpus once, with nothing else running

This is the only step that writes, and it comes in two parts, because the FindFacts indexer writes the very Lucene index the `solr` service holds open — the two must never have it at the same time.

**1a. Index, with Solr stopped.** This installs Isabelle and the AFP and runs `isabelle find_facts_index`. The first run downloads the pinned Isabelle distribution (~1.2 GB, contrib and a JDK included) and clones the AFP; indexing the whole AFP then takes about a day.

```bash
docker compose run --rm tools python -m src.corpus --index-only
```

**1b. Build the corpora, with Solr running.** This fetches the documents from Solr, informalizes every theorem and definition and embeds them. Expect days for the whole AFP; it is resumable, so an interrupted run continues where it stopped.

```bash
docker compose up -d solr
docker compose run --rm tools python -m src.corpus
```

1b starts by re-checking the index, which is a no-op as long as the session list has not changed since 1a — so repeating it is normally free. It is not free if the list *has* changed: 1b updates the AFP first, and with `"isabelle_sessions": ["all"]` the session list is read from the AFP's `thys/ROOTS`, so an update that brings in new entries makes it want to index again while Solr holds the index open. It then aborts with an error naming that as the cause. That is not damage — nothing was written — but the remedy is to stop Solr, run 1a again and then 1b. Set `"check_for_updates": false` to keep the AFP still across a build.

#### 2. Serve

The website runs read-only: nothing is cloned, indexed, fetched, informalized, embedded or pruned, and a missing corpus is reported instead of being built.

```bash
docker compose up -d
```

`waitress` is configured with `threads=1`, and the LLM output cache the website writes (`.cache/llm_output_cache.json`) has no locking, so **exactly one `app` container may run.** That file also grows for as long as the site is up; set `"enable_llm_output_cache": false` if that is not wanted, at the cost of repeating every query refinement after a restart.

An analysis runs alongside it. It is read-only too and writes only its own LLM cache and its report:

```bash
docker compose run --rm tools python -m src.duplicates --newest 10
```

Two things to keep in mind while both run:

- They compete for the same LLM and embedding servers. Start `llama-server` with `--parallel 2` (raising `-c`, which is divided across the slots) so a long analysis cannot block the website. Adding `--no-llm-judge` to the analysis removes its LLM load entirely; only the `likely` tier is lost.
- Each process holds the corpora it uses in memory, so plan for roughly `(theorems + definitions) × 15 KB` per process with a 2560-dimensional embedding model. The analysis only loads the corpora it actually queries, i.e. `--kinds definitions` never loads the theorems.

`api_port` (5001 by default) is published directly. Put a reverse proxy with TLS in front of it before the site is reachable from outside.

### Pinned Isabelle and AFP versions

`config.json` pins both components under `"components"`, and they have to move together — an AFP release checkout does not build against a development Isabelle.

```json
"isabelle": {
    "archive_url": "https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/Isabelle2025-2_linux.tar.gz",
    "version": "Isabelle2025-2",
    "local_folder": "Isabelle"
},
"afp": {
    "remote_url": "https://github.com/isabelle-prover/mirror-afp-2025-2.git",
    "local_folder": "afp",
    "target_branch": "master"
}
```

Isabelle is installed from its release archive rather than from git, because the Isabelle git mirror only carries the development branch and has no release branches or tags. `version` is checked against `etc/ISABELLE_IDENTIFIER` in the installed tree, so an already installed release is never downloaded twice.

`archive_url` points at the Cambridge mirror rather than at `isabelle.in.tum.de/dist/...`, because the canonical URL 301-redirects to plain HTTP on `dist.isabelle.cit.tum.de`, which was unreachable from every network this was tried on. The three mirrors that the [Isabelle homepage](https://isabelle.in.tum.de/) lists all serve the identical file directly over HTTPS with no redirect, and any of them can be used:

```
https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/Isabelle2025-2_linux.tar.gz
https://mirror.clarkson.edu/isabelle/dist/Isabelle2025-2_linux.tar.gz
https://proofcraft.systems/isabelle/dist/Isabelle2025-2_linux.tar.gz
```

Whatever `archive_url` points at is checked twice: the download has to match the length the server announced, and the extracted tree has to identify itself as `version` through `etc/ISABELLE_IDENTIFIER`. A truncated download and a wrong archive are both reported instead of installed. A mirror may lag by a day or two after a new Isabelle release, so on a version bump check that it already carries the new file.

The AFP is a shallow clone of the release mirror for the matching year. The release mirrors are separate repositories, each with a single `master` branch, so a version bump changes `remote_url`, not `target_branch`. `afp_remote_thys_folder_url` links search results to the sources and has to be moved to the same release.

Neither component is ever overwritten in place: if `Isabelle/` holds a different release, or `afp/` is a checkout of a different remote, the build stops and names the folder to remove. That is deliberate — a tree that is half one release and half another only shows up much later as build errors.

### Updating to a newer AFP version

Serving processes never write, so an update is a maintenance window:

1. Stop the web application and any running analysis (`docker compose down`).
2. Run the two build steps above. Step 1a pulls the AFP and re-indexes the changed sessions with FindFacts; step 1b then brings all three artifacts back in line automatically:
   - the document index is refetched from Solr, because its fingerprint (`.cache/*.fingerprint.json`) no longer matches the corpus,
   - only new and changed documents are informalized, since descriptions are keyed by a checksum of the source code,
   - the ChromaDB collections lose the documents that the AFP removed, re-embed the ones whose source code changed and embed the new ones.
3. Start the web application again. It reads the corpus once at start-up, so it will not pick up a rebuilt corpus without a restart.

A move to a new *release* — say from 2025-2 to 2026 — is the same maintenance window plus the version bump described above: edit both pins, remove `Isabelle/` and `afp/` from the volume when the build tells you to, and let it reinstall.

If a rebuild would remove more than half of a collection, it aborts instead: that is not an AFP update but a sign that the document index does not belong to the collection (usually a wrong `solr_query` or `chroma_db_path`). Delete the collection by hand if the corpus really did shrink that much.

Two things are not automatic. After an Isabelle version bump the heap images of the previous version stay in `~/.isabelle/heaps/polyml-*` and can be deleted by hand, which matters because they run to tens of gigabytes for the whole AFP. FindFacts backups in `~/.isabelle/` are pruned to the newest `find_facts_backup_keep` (2 by default; set it to a negative number to keep all of them).

### Migration: descriptions are now cut at `<END>`

Loading a description used to cut only at `<BEGIN>`, so anything a model emitted after `<END>` — trailing reasoning, pleasantries — stayed in the description and in the embedding built from it. The parsing now cuts at both markers.

The rebuild machinery cannot pick this up on its own: the checksum stored next to each embedding covers the source code only, and neither the sources nor the raw artifacts changed — only how they are parsed. Collections embedded before this change therefore keep serving vectors of the old, longer text until they are rebuilt by hand:

1. Stop everything (`docker compose down`).
2. Delete the ChromaDB storage (the folder at `chroma_db_path`).
3. Run the corpus build again (step 1b above). It re-embeds everything from the existing descriptions artifact — the raw LLM outputs on disk are untouched and are **not** informalized again, so this costs hours of embedding, not days of LLM calls.

Skipping the rebuild does not break anything; search just keeps ranking against the old embedded text until the next full rebuild.

### Tests

The tests use only the Python standard library's `unittest`, so they need no additional packages. Run them inside the root folder of the repository:

```bash
python3 -m unittest discover -s tests -t .
```

`tests/test_openai_backends.py`, `tests/test_serve_and_update.py` and `tests/test_installation.py` run offline against a stub server and need neither a network, nor Solr, nor git, nor a GPU machine. `tests/test_serve_and_update.py` covers what a deployment depends on: that a serving process never writes, that an AFP update invalidates the document index cache, deletes documents the AFP removed and re-embeds the ones whose source code changed, and that an unreachable Solr is reported by name instead of prompting a server that has no terminal. `tests/test_installation.py` covers the pinned components: that a release is installed from its archive exactly once and that a checkout of a different release or remote is reported instead of overwritten. `tests/test_server_availability.py` talks to the servers configured in `config.json`: it checks that both are reachable, that the configured models answer, and that the embedding server accepts a document of `openai_embedding_max_characters` as well as a full batch of `openai_embedding_batch_size` — which is what catches a physical batch size that is too small. It needs the API key exported and is skipped automatically when the backends are not set to `openai`. To run it alone:

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
