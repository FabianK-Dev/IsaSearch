# Deployment plan

Working document for deploying IsaSearch on a university server. It is written to be read without
any prior conversation: it states the architecture, what is already implemented, what is left, and
how to verify each step. Delete it once the deployment is done.

Branch: `duplicate-detection`. Everything described under "Already done" is in commit `e83e410`.

## 1. Target deployment

One server, reachable as a website, running two processes at the same time:

- the web application (`python -m src.app`), serving the search UI and REST API,
- the duplicate detection (`python -m src.duplicates --serve …`), run on demand by a maintainer.

Both share one Solr index, one set of LLM informalisations and one ChromaDB storage. The corpus is
built on the same machine and is rebuilt when the AFP is updated.

Hardware requested: **64 GB RAM, 500 GB disk.** See section 7 for what those numbers are based on
and what still has to be measured.

## 2. The architecture, and why

The whole design rests on one invariant:

> Every artifact has exactly one writer.

That is achieved by splitting every entry point into two modes (`boot_components(serve=...)` in
[src/bootstrap.py](../src/bootstrap.py)):

- **Build mode** (`serve=False`) — the only process that may write. It updates Isabelle and the AFP,
  builds the FindFacts index, fetches the document indexes from Solr, informalizes what is missing,
  and embeds and prunes the ChromaDB collections. Run alone, in a maintenance window.
- **Serve mode** (`serve=True`) — any number of processes, strictly read-only. Every one of those
  steps is turned off. A corpus that was not built beforehand is reported, never built.

Because serving never writes, the two serving processes cannot corrupt each other's state, and no
locking or coordination between them is needed.

Isabelle installs itself: [check_and_update](../src/installation.py) clones the Isabelle and AFP
mirrors (`--depth 1`) and [setup_isabelle_components](../src/installation.py) runs
`isabelle components -I` and `-a` to fetch the contrib components. There is no manual installation
step anywhere — but it needs `git` on the PATH, which matters for the container (task 2).

## 3. Already done (commit `e83e410`)

Do not redo these; read them for context.

| Area | What |
|---|---|
| Serve mode | `boot_components(serve=True)` overrides `check_updates`/`build_find_facts`, passes `generate_missing=False` and `add_missing=False`, forces `DEFINITIONS_LOAD`, and skips the tokenizer. `src/app.py` always uses it; `src/duplicates.py` has `--serve`. |
| LLM cache | The duplicate detection owns `llm_output_cache_dedup.json` (`config["dedup_llm_cache"]`). All writes are atomic (temp file + `os.replace`). |
| Index invalidation | `build_document_index` writes a fingerprint (`solr_query`, session list, Solr document count) next to the cache and refetches when it no longer matches. Previously an AFP update stayed invisible forever. |
| ChromaDB reconciliation | Embeddings store an Adler32 checksum of their source. A build deletes documents that left the corpus and re-embeds those whose source changed. Refuses to delete >50 % of a collection. |
| Memory | Corpora that a run never queries are not loaded (`--kinds definitions` skips the theorem corpus). `torch` and `transformers` are imported lazily. |
| Housekeeping | FindFacts backups pruned to `config["find_facts_backup_keep"]` (default 2). Reports name the actually configured embedding model. |
| Tests | `tests/test_serve_and_update.py`, 24 offline tests. |
| Docs | README sections "Running on a server" and "Updating to a newer AFP version". |

## 4. Decisions already taken

- **Keep Docker, restructure it.** The image becomes code + Python dependencies only. All mutable
  state moves to volumes. The same image serves three roles (build, website, analysis). Rationale:
  the dependency set is heavy and version-sensitive (`chromadb==1.4.1`, `torch`, `transformers`,
  `pandas==3.0.0`), the deployment is long-lived, and a pinned interpreter removes a whole class of
  failure. Baking corpora into the image is dropped — at full-AFP scale that is a ~25 GB image
  rebuilt on every corpus update.
- **Solr becomes its own service**, so both serving processes can reach it.
- **The build runs in a container too** (same image, different command), since Isabelle installs
  itself. There is no native-host installation step.

## 5. Open decisions — ask the user before implementing

1. **`waitress` threads.** [src/app.py](../src/app.py) ends with `serve(app, …, threads=1)`, so the
   site handles one request at a time; a slow LLM query refinement blocks every other visitor.
   Raising it requires auditing shared mutable state first — `llm_output_cache` is a plain dict
   mutated during search, and `search()` writes it. For a low-traffic academic site, keeping 1 is
   defensible. **Do not change this without asking.**
2. **Reverse proxy and TLS** in front of `config["api_port"]` (5001) — depends on what the
   university provides.
3. **Embedding dimension.** Currently Qwen3-Embedding-4B at 2560 dimensions. Truncating to 1024
   (the model is Matryoshka-trained) would roughly halve vector RAM and disk. No longer required for
   capacity reasons, so treat as optional; it needs a full re-embed and a fresh `chroma_db_path`.

## 6. Tasks

Ordered. Each has an acceptance criterion. Tasks 1–5 need no server and can be done immediately.

### Task 1 — Make Solr connection non-interactive (do this first, independent of everything else)

**Problem.** [connect_solr](../src/solr.py) calls
`input("Solr seems to be down. Do you want to start a local Solr instance via Docker? [Y/n]: ")`
when the ping fails. Under systemd or `docker run -d` there is no TTY, so this raises `EOFError` and
the process dies with a confusing traceback instead of a clear error. `start_local_solr` then shells
out to `docker run solr:latest`, which is wrong on a server and incoherent inside a container. It
also reads `config["isabelle_version"]`, which serve mode no longer sets.

**Do.** Only offer the interactive path when `sys.stdin.isatty()`. Otherwise raise a `RuntimeError`
naming `config["solr_core_url"]` and saying Solr has to be running. Keep the interactive path for
local development. Consider gating it further behind an explicit config key.

**Accept.** With Solr down and stdin closed (`python -m src.app < /dev/null`), the process exits
with a one-line error mentioning the Solr URL, and no traceback from `input()`. Add a test.

### Task 2 — Restructure the Dockerfile

**Problem.** [Dockerfile](../Dockerfile) has not been touched in 15 commits (last change
2026-04-28, before `bootstrap.py`, the duplicate detection and the openai/llamacpp backends). It has
three concrete defects:

- **No `git`.** It installs only `wget` and `openjdk-17-jre-headless`. `config.json` sets
  `"check_for_updates": true`, so `check_and_update` runs `subprocess.run(["git", …])` at every
  start, which raises `FileNotFoundError` — and that function catches only `CalledProcessError`.
- **Path mismatch.** It copies the AFP to `/app/afp-2025-branch-default` while `config.json` expects
  `components.afp.local_folder == "afp"`.
- It bakes `chroma_storages`, the Solr index and the AFP checkout into the image, and installs Solr
  inside the app container.

**Do.**
- Add `git` to the `apt-get install` line.
- Remove the Solr download/install and the `COPY ./assets_extracted/…` lines.
- Keep `COPY requirements.txt` + `pip install`, and the code copies (`src`, `prompts`, `benchmark`,
  `config.json`).
- Set `HOME` to a state directory (e.g. `/data/home`) so that `~/.isabelle` — contrib, heaps and the
  FindFacts Solr core — lands on the mounted volume rather than in the container layer.
- Replace `CMD` with the app only; the build and analysis roles get their command at run time.

**Accept.** `docker build` succeeds. `docker run --rm <image> git --version` works.
`docker run --rm <image> python -c "import chromadb, flask, pysolr"` works.

### Task 3 — Add a compose file

**Do.** Add `compose.yaml` with three services, all using the same image:

- `solr` — official Solr image, serving the core from the shared state volume
  (`$HOME/.isabelle/find_facts/solr/local`), published on 8983.
- `app` — `python -m src.app`, depends on `solr`, publishes `api_port`.
- `tools` — profile-gated or `run`-only, for
  `docker compose run --rm tools python -m src.duplicates --serve --newest 10`
  and for the build, `… python -m src.duplicates --build-corpus-only`.

All three mount one state volume. Everything mutable must be under it: `~/.isabelle` (contrib,
heaps, Solr core), the `Isabelle/` and `afp/` checkouts, `.cache/`, `artifacts/`, `chroma_storages/`.
Prefer one mount over six by rooting the config's relative paths inside it.

**Accept.** `docker compose up solr` starts Solr against the shared volume. `docker compose run --rm
tools python -m src.duplicates --serve --newest 1` reaches Solr and fails with the "corpus not
built" message rather than a connection error.

### Task 4 — Rewrite `docker_build.sh`

**Problem.** It does `cp .gitignore .dockerignore`, then removes only the `assets_extracted` line.
`.cache` is the second line of `.gitignore`, so the cache directory is excluded from the build
context by construction. With the assets no longer baked in, all of this disappears.

**Do.** Reduce it to `docker build` + tag + push. Drop the tarball extraction and the
`.dockerignore` juggling. Write a real `.dockerignore` instead of generating one.

**Accept.** The script no longer references `assets/` or `assets_extracted/`.

### Task 5 — Update the README deployment section

**Do.** Rewrite "Running on a server" for the container model: one image, three commands, one state
volume, Solr as a service. Keep the build/serve explanation and the update runbook — only the
invocation changes. Document that the first build downloads Isabelle plus 10–15 GB of contrib.

**Accept.** A reader who has only the README can deploy from scratch.

### Task 6 — Dry run on a subset (needs the server)

Do **not** start the full AFP build before this. The full build takes days; a config error found 30
hours in is expensive.

**Do.** Keep `"isabelle_sessions": ["Ramsey-Infinite", "Ordinals_and_Cardinals"]`, set the production
paths and export the API key. Run the build, then start the app and an analysis in parallel.
While it runs, measure (see section 7).

**Accept.** Build completes; the website answers a search; `--serve` produces a report; neither
process writes a file the other owns (check timestamps on `.cache/`, `artifacts/`, `chroma_storages/`).

### Task 7 — Production config and full build (needs the server)

**Do.** Set `"isabelle_sessions": ["all"]`, point `chroma_db_path`/`artifacts_folder`/`cache_folder`
at the state volume, export `ISASEARCH_API_KEY`, confirm the LLM and embedding server URLs are
reachable from inside the container. Then run `--build-corpus-only` and let it run.

**Accept.** `python3 -m src.duplicates --serve --newest 10` produces a report whose self-retrieval
control passes (the run exits non-zero if more than 5 % of documents fail to retrieve themselves).

### Task 8 — Service management and exposure (needs the server)

**Do.** systemd units wrapping `docker compose` (or the equivalent), a reverse proxy with TLS in
front of `api_port`, and a decision on task-5-open-item 1 (`threads`). Restart policy: the app must
come up after `solr`.

## 7. Numbers, and what still has to be measured

These estimates went through two rounds of correction. Treat the measured ones as reliable and the
extrapolated ones as provisional.

**Measured (reliable).** ChromaDB holds its vectors in private, non-shared, non-evictable memory:
three processes on one collection each held their own full copy, with only 304 KB file-backed. The
cost is `N × dim × 4 bytes × ~1.05` plus about 80 MB of fixed overhead per process. At
dim 2560 that is 10.6 KB per vector. The document index costs roughly 2–3 KB per document.

```
RAM per process ≈ 0.5 GB + (documents it loads) × 14 KB
```

The website loads theorems + definitions; an analysis with `--kinds definitions` loads only the
definitions; `--cross` or `--kinds all` loads both.

**Extrapolated (verify during task 6).**

| Corpus (thm + def) | Website | Analysis (definitions) | Both |
|---|---|---|---|
| 400k | 6.1 GB | 1.9 GB | 8 GB |
| 700k | 10.3 GB | 3.3 GB | 13.6 GB |
| 1.1M | 15.9 GB | 4.7 GB | 20.6 GB |

Disk, full AFP: heaps 10–25 GB (only *parent* sessions get heap images — `find_facts_index` does not
store heaps for the sessions it indexes, confirmed on the 2026-04-28 run where `Ramsey-Infinite` and
`Ordinals_and_Cardinals` produced session databases but no heaps), session databases 2–5 GB, Isabelle
contrib 10–15 GB, shallow clones 2–4 GB, Solr index 5–15 GB, ChromaDB ~8 GB, caches and artifacts
~4 GB. Total roughly **45–80 GB**, so 500 GB is generous.

**Still unmeasured — do these in task 6:**

1. **Actual document counts.** With Solr running:
   ```bash
   python3 -c "from src.bootstrap import load_config; from src.solr import connect_solr, count_docs; c=load_config(); s=connect_solr(c); print('theorems', count_docs(s, c['solr_query'])); print('definitions', count_docs(s, c['solr_query_definitions']))"
   ```
   Put the result into the RAM formula above.
2. **Isabelle build memory.** This is the likely peak on the whole machine and the main reason for
   64 GB rather than 32 GB. Measure peak RSS during `isabelle build` and tune `-j` accordingly.
3. **Disk growth per session.** Measure `du -sh ~/.isabelle` before and after building 20–30 diverse
   sessions (include a few known-heavy AFP entries) and extrapolate to ~1000 sessions.

If 32 GB turns out to be all that is available: serving fits in every scenario above. The two
constraints are that `--cross` / `--kinds all` analyses should then run in a maintenance window
rather than alongside the site, and that Isabelle's `-j` has to be tuned for the build.

## 8. Verification

Offline tests, no network, no Solr, no GPU server:

```bash
python3 -m unittest discover -s tests -t .
```

Expect all to pass except `tests/test_server_availability.py`, which needs `ISASEARCH_API_KEY`
exported and the configured servers reachable. Formatting and linting:

```bash
nix shell nixpkgs#ruff -c ruff format src tests benchmark
```

`ruff check` currently reports 26 pre-existing findings across the codebase; keep that number from
growing rather than trying to reach zero.
