# Deployment plan

Working document for deploying IsaSearch on a university server. It is written to be read without
any prior conversation: it states the architecture, what is already implemented, what is left, and
how to verify each step. Delete it once the deployment is done.

Branch: `duplicate-detection`. **Tasks 1–5 are done** (see section 3b); tasks 6–8 need the server.

## 1. Target deployment

One server, reachable as a website, running two processes at the same time:

- the web application (`python -m src.app`), serving the search UI and REST API,
- the duplicate detection (`python -m src.duplicates …`), run on demand by a maintainer.

Both read one Solr index, one set of LLM informalisations and one ChromaDB storage, all produced by
a third process, the corpus build (`python -m src.corpus`), which runs alone on the same machine and
is re-run when the AFP is updated. All three roles run from the same container image against one
state volume; see [compose.yaml](../compose.yaml).

Hardware requested: **64 GB RAM, 500 GB disk.** See section 7 for what those numbers are based on
and what still has to be measured.

## 2. The architecture, and why

The whole design rests on one invariant:

> Every artifact has exactly one writer.

That is achieved by splitting every entry point into two modes (`boot_components(serve=...)` in
[src/bootstrap.py](../src/bootstrap.py)):

- **Build mode** (`serve=False`) — the only process that builds. It updates Isabelle and the AFP,
  builds the FindFacts index, fetches the document indexes from Solr, informalizes what is missing,
  and embeds and prunes the ChromaDB collections. Run alone, in a maintenance window.
- **Serve mode** (`serve=True`) — read-only with respect to the corpus. Every one of those steps is
  turned off. A corpus that was not built beforehand is reported, never built.

**Correction (this is not what an earlier version of this document claimed).** Serve mode is not
write-free. The web application writes `.cache/llm_output_cache.json` on every query refinement that
was not cached yet ([src/embeddings.py](../src/embeddings.py), `save_llm_output_cache`), and the
duplicate detection writes its own `llm_output_cache_dedup.json`. The invariant that actually holds
is the weaker per-file one: the two serving processes use different cache names, so they never write
the same file — but **only one web application process may run**, because that file has no locking.
`threads=1` in [src/app.py](../src/app.py) is what serialises writes within that process, which is a
second reason not to raise it (section 5). The file also grows for as long as the site is up;
`"enable_llm_output_cache": false` turns it off at the price of repeating every refinement after a
restart. It is deliberately left on.

Isabelle and the AFP install themselves; there is no manual installation step anywhere.
[check_and_update](../src/installation.py) dispatches on the component's configuration: Isabelle is
installed from its release archive (`archive_url` + `version`) and the AFP from a shallow git clone
(`remote_url` + `target_branch`). See section 4a for why they differ.

## 3. Already done (commit `e83e410`)

Do not redo these; read them for context.

| Area | What |
|---|---|
| Serve mode | `boot_components(serve=True)` overrides `check_updates`/`build_find_facts`, passes `generate_missing=False` and `add_missing=False`, and forces `DEFINITIONS_LOAD`. `src/app.py` always uses it; `src/duplicates.py` did so through `--serve`, and unconditionally since the corpus build became `src/corpus.py`. |
| LLM cache | The duplicate detection owns `llm_output_cache_dedup.json` (`config["dedup_llm_cache"]`). All writes are atomic (temp file + `os.replace`). |
| Index invalidation | `build_document_index` writes a fingerprint (`solr_query`, session list, Solr document count) next to the cache and refetches when it no longer matches. Previously an AFP update stayed invisible forever. |
| ChromaDB reconciliation | Embeddings store an Adler32 checksum of their source. A build deletes documents that left the corpus and re-embeds those whose source changed. Refuses to delete >50 % of a collection. |
| Memory | Corpora that a run never queries are not loaded (`--kinds definitions` skips the theorem corpus). `torch` and `sentence-transformers` are imported lazily, and only by the `sentence_transformers` embedding backend. |
| Housekeeping | FindFacts backups pruned to `config["find_facts_backup_keep"]` (default 2). Reports name the actually configured embedding model. |
| Tests | `tests/test_serve_and_update.py`, 24 offline tests. |
| Docs | README sections "Running on a server" and "Updating to a newer AFP version". |

## 3b. Also done — tasks 1–5

| Task | What |
|---|---|
| 1 | `connect_solr` only offers the interactive Docker fallback when `sys.stdin.isatty()`; otherwise it raises a `RuntimeError` naming `solr_core_url`, chained from the original error. `start_local_solr` no longer gates on the unused `isabelle_version` and its readiness loop actually pings instead of only constructing a client. |
| 2 | [Dockerfile](../Dockerfile) rewritten: code + dependencies only, `git` installed, no Solr, no baked assets, `HOME=/data/home`, the state directories symlinked out of `/app` onto the volume, `EXPOSE 5001`, and [docker-entrypoint.sh](../docker-entrypoint.sh) creating the volume targets so the symlinks never dangle. |
| 3 | [compose.yaml](../compose.yaml): `solr`, `app` and a `run`-only `tools` service, one named `state` volume, the server's `config.json` bind-mounted, `ISASEARCH_API_KEY` passed through. |
| 4 | `docker_build.sh`, `docker_push.sh`, `docker_run.sh` and `solr_db.sh` deleted — `docker compose build` replaces them and the registry push is no longer wanted. `.dockerignore` is now a real checked-in file instead of a copy of `.gitignore` (which excluded `.cache` and `afp/` from the context by construction). |
| 5 | README rewritten for the container model, plus a new "Pinned Isabelle and AFP versions" section. |
| — | Isabelle and the AFP pinned to 2025-2, see section 4a. |
| — | `src/installation.py` no longer reads `config.json` at import time; `setup_isabelle_components` and `get_isabelle_version` take the config. A checkout of a different remote, or an installation of a different release, is now reported instead of being pulled into or overwritten. |
| — | The build is split in two. `isabelle find_facts_index` writes the same Lucene index the `solr` service holds open, so it has to run with the service stopped — but everything after it needs the service up, and it is all one `boot_components` call. The part before Solr is now `prepare_corpus_sources` in `src/bootstrap.py`, reachable on its own as `python -m src.corpus --index-only`. Without it, the documented single build command could not succeed on a fresh volume. |
| — | LLM completion requests had `timeout=None` on all three backends. One wedged response would have frozen the site permanently, since `threads=1` and the process stays alive so `restart: unless-stopped` never fires. Now bounded by `config["llm_request_timeout"]` (600 s). |
| — | `prompts/qwen3-gemma/` — the folder `config.json` actually points at — was missing `describe_definition.txt` and `duplicate_judge.txt`; only the `microsoft-Phi` folders got them when the duplicate detection was added. The build would have raised `KeyError` after days of theorem informalization and before any embedding, and every LLM-judged analysis would have crashed. Both prompts added, to the `-with-metadata` variant as well. |
| — | A failed `isabelle find_facts_index` was caught and only printed. As a standalone step (`--index-only`) that exit status is the only signal a runbook has, so it now raises, with the "Solr is still holding the index" cause named. `setup_isabelle_components` still only warns, on purpose. |
| — | With `--kinds all`, entries were selected on the definitions corpus alone, so an entry that has theorems but no definitions of its own was reported as "not part of the corpus" and never analysed. Selection now spans every requested kind. |
| — | `config["tokenizer_name"]` and the tokenizer it loaded are gone. The tokenizer existed only to compute a `max_tokens` value that was printed and never used, and it named Phi-3.5 while the configured document model is a Gemma, so the number was for the wrong tokenizer family. It also made the first build in a fresh container reach huggingface.co — on a server that cannot, the build died at "Loading tokenizer..." before doing any work. |
| — | `setup_isabelle_components` ran `isabelle components -I` and `-a` against a *release* distribution. Those are repository operations: `-I` writes an `init_components` line into `$ISABELLE_HOME_USER/etc/settings` pointing at `$ISABELLE_HOME/Admin/components/main`, which a release does not ship, so every later `isabelle` call aborted with "Bad component catalog file" and the build died at `get_isabelle_version`. The setup is now skipped for archive-installed components, which already carry their contrib. **Recovering an installation that already ran it: remove `~/.isabelle/Isabelle2025-2/etc/settings`** (the whole `~/.isabelle/Isabelle2025-2/etc/` directory is safe to remove; Isabelle recreates what it needs). |
| — | Building the corpus was a flag on the duplicate detection (`--build-corpus-only`), so the runbook told an operator to invoke the duplicate detector in order to start the website. The corpus is shared infrastructure with two readers, so it got its own entry point, [src/corpus.py](../src/corpus.py) (`python3 -m src.corpus`, with `--index-only` for the Solr-stopped phase). `src/duplicates.py` is now the analysis only and is unconditionally read-only; its `--serve` flag is gone because there is nothing left for it to switch. The command is named by a dozen "build the corpus first" messages, so it has one owner, `BUILD_CORPUS_COMMAND` in `src/documents.py`. |
| Tests | `tests/test_installation.py` (new) and a `SolrConnectionTest` in `tests/test_serve_and_update.py`; 72 offline tests pass. |

Defects found on the way that this document did not name: `docker build` failed outright
(`COPY artifacts` — the directory is untracked and absent), `docker_run.sh` published 5000 while the
app binds `api_port` 5001, `solr_core_url` was `localhost`, `solr_db.sh` pointed at
`/home/fabian/.isabelle/Isabelle_16-May-2025/…`, and `docker_build.sh` used GNU `sed -i` on a macOS
checkout.

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

## 4a. Pinning Isabelle and the AFP to 2025-2

The AFP is pinned by pointing `components.afp.remote_url` at
`https://github.com/isabelle-prover/mirror-afp-2025-2.git`, the release mirror for the matching
year. The release mirrors are separate repositories with a single `master` branch, so a version bump
changes the URL, not the branch. `afp_remote_thys_folder_url` moves with it, otherwise search results
link to devel revisions.

Isabelle **cannot** be pinned the same way, which is the trap here: setting
`target_branch: "Isabelle2025-2"` on `mirror-isabelle` looks right and does not work. That mirror has
only `master` (devel) plus a dependabot branch, and its newest tag is `Isabelle2021-1-RC5`; it is the
only Isabelle repository in the `isabelle-prover` organisation. A commit-SHA pin was rejected too:
releases are cut on a Mercurial release branch that is not on the mirrored default branch, so no ref
identifies the release commit, and it would force a full clone. Cloning upstream Mercurial at tag
`Isabelle2025-2` would add an `hg` dependency and re-download contrib for nothing.

So Isabelle is installed from its official release archive, which is versioned and bundles contrib
**and** a JDK — which is why the image needs neither `openjdk-17-jre-headless` nor a
separate 10–15 GB contrib download. The installed tree identifies itself through
`etc/ISABELLE_IDENTIFIER`, which is compared against the configured `version`, so a release is
downloaded exactly once and a differing installation is reported rather than replaced.

**Not** from the canonical `https://isabelle.in.tum.de/dist/...`, though: that 301-redirects to
plain HTTP on `dist.isabelle.cit.tum.de`, which was unreachable from every network this was tried
on — the development machine and the user's. Two earlier versions of this document got this wrong,
first recommending the canonical URL and then an HTTPS mirror that does not work either.

`archive_url` therefore points at the Cambridge mirror,
`https://www.cl.cam.ac.uk/research/hvg/Isabelle/dist/Isabelle2025-2_linux.tar.gz`. All three mirrors
the Isabelle homepage lists (Cambridge, mirror.clarkson.edu, proofcraft.systems) were verified to
serve the identical 1,228,480,874-byte file directly over HTTPS with no redirect. Cambridge is the
default because it is one of Isabelle's two home institutions and therefore the most durable of the
three. Upstream publishes no checksum next to the archive, so integrity rests on the two checks the
installer does: the download must match the announced Content-Length, and the extracted tree must
identify itself as `version`. Adding a `sha256` to the component config would close that gap and is
worth doing if the mirror is ever considered untrusted.

Both components must move together: an AFP release checkout does not build against a devel Isabelle,
so pinning one and not the other is worse than pinning neither.

## 5. Open decisions — ask the user before implementing

1. **`waitress` threads.** [src/app.py](../src/app.py) ends with `serve(app, …, threads=1)`, so the
   site handles one request at a time; a slow LLM query refinement blocks every other visitor.
   Raising it requires auditing shared mutable state first — `llm_output_cache` is a plain dict
   mutated during search, and `search()` writes it. For a low-traffic academic site, keeping 1 is
   defensible. **Do not change this without asking.** *Decided: it stays at 1. See the correction in
   section 2 — `threads=1` is what serialises the cache writes, so raising it is a correctness
   change, not a throughput knob.*
2. **Reverse proxy and TLS** in front of `config["api_port"]` (5001) — depends on what the
   university provides.
3. **Embedding dimension.** Currently Qwen3-Embedding-4B at 2560 dimensions. Truncating to 1024
   (the model is Matryoshka-trained) would roughly halve vector RAM and disk. No longer required for
   capacity reasons, so treat as optional; it needs a full re-embed and a fresh `chroma_db_path`.

## 6. Tasks

Ordered. Each has an acceptance criterion. **Tasks 1–5 are done** — what was actually changed is in
section 3b, and the descriptions below are kept only so that the acceptance criteria can be re-run.
Tasks 6–8 need the server.

### Task 1 — Make Solr connection non-interactive — DONE

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

### Task 2 — Restructure the Dockerfile — DONE

**Problem.** [Dockerfile](../Dockerfile) had not been touched in 15 commits (last change
2026-04-28, before `bootstrap.py`, the duplicate detection and the openai/llamacpp backends). It has
three concrete defects:

- **No `git`.** It installs only `wget` and `openjdk-17-jre-headless`. `config.json` sets
  `"check_for_updates": true`, so `check_and_update` runs `subprocess.run(["git", …])` at every
  start, which raises `FileNotFoundError` — and that function catches only `CalledProcessError`.
- **Path mismatch.** It copies the AFP to `/app/afp-2025-branch-default` while `config.json` expects
  `components.afp.local_folder == "afp"`.
- It bakes `chroma_storages`, the Solr index and the AFP checkout into the image, and installs Solr
  inside the app container.
- Not named when this was written: it did not build at all. `COPY artifacts /app/artifacts` refers to
  a directory that is neither present nor tracked, as do the `assets/` tarballs `docker_build.sh`
  extracted.

**Do.**
- Add `git` to the `apt-get install` line.
- Remove the Solr download/install and the `COPY ./assets_extracted/…` lines.
- Keep `COPY requirements.txt` + `pip install`, and the code copies (`src`, `prompts`, `benchmark`,
  `config.json`).
- Set `HOME` to a state directory (e.g. `/data/home`) so that `~/.isabelle` — contrib, heaps and the
  FindFacts Solr core — lands on the mounted volume rather than in the container layer.
- Replace `CMD` with the app only; the build and analysis roles get their command at run time.

**Accept.** `docker compose build` succeeds. `docker run --rm isasearch git --version` works.
`docker run --rm isasearch python -c "import chromadb, flask, pysolr"` works.
`docker run --rm isasearch python -m unittest discover -s tests -t .` runs the offline tests inside
the image (`tests/` is copied in precisely for this smoke test; the `test_server_availability` errors
are expected without the API key and the servers). **Not yet run — no Docker daemon was available on
the development machine.**

### Task 3 — Add a compose file — DONE

**Do.** Add `compose.yaml` with three services, all using the same image:

- `solr` — official Solr image, serving the core from the shared state volume
  (`$HOME/.isabelle/find_facts/solr/local`), published on 8983.
- `app` — `python -m src.app`, depends on `solr`, publishes `api_port`.
- `tools` — profile-gated or `run`-only, for
  `docker compose run --rm tools python -m src.duplicates --newest 10`
  and for the build, `… python -m src.corpus`.

All three mount one state volume. Everything mutable must be under it: `~/.isabelle` (contrib,
heaps, Solr core), the `Isabelle/` and `afp/` checkouts, `.cache/`, `artifacts/`, `chroma_storages/`.
Prefer one mount over six by rooting the config's relative paths inside it.

**Accept.** `docker compose up solr` starts Solr against the shared volume. `docker compose run --rm
tools python -m src.duplicates --newest 1` reaches Solr and fails with the "corpus not
built" message rather than a connection error or an `EOFError`. **Not yet run — no Docker daemon.**
Note that this check on an empty volume starts Solr before any index exists; wipe
`~/.isabelle/find_facts/solr` on the volume before the real build so that nothing Solr created is
mistaken for a FindFacts core.

### Task 4 — Replace the Docker helper scripts — DONE

**Problem.** `docker_build.sh` did `cp .gitignore .dockerignore`, then removed only the
`assets_extracted` line. `.cache` is the second line of `.gitignore` and `afp*/` the tenth, so both
were excluded from the build context by construction. It also used GNU `sed -i`, which fails on
macOS, and extracted tarballs from an `assets/` directory that does not exist.

**Done.** All four scripts (`docker_build.sh`, `docker_push.sh`, `docker_run.sh`, `solr_db.sh`) are
deleted: `docker compose build` replaces the build and the registry push is no longer wanted.
`.dockerignore` is a real checked-in file.

**Accept.** No script references `assets/` or `assets_extracted/`; nothing generates `.dockerignore`.

### Task 5 — Update the README deployment section — DONE

**Done.** "Running on a server" rewritten for the container model: one image, three roles, one state
volume, Solr as a service, plus a new "Pinned Isabelle and AFP versions" section. The build/serve
explanation and the update runbook are kept. The first-build download is **~1.2 GB for the Isabelle
distribution, contrib included** — the "Isabelle plus 10–15 GB of contrib" figure applied to the git
install and no longer holds.

**Accept.** A reader who has only the README can deploy from scratch.

### Task 6 — Dry run on a subset (needs the server)

Do **not** start the full AFP build before this. The full build takes days; a config error found 30
hours in is expensive.

**Do.** Keep `"isabelle_sessions": ["Ramsey-Infinite", "Ordinals_and_Cardinals"]`, set
`solr_core_url` to `http://solr:8983/solr/local` and put the API key in `.env`. Run the build, then
start the app and an analysis in parallel. While it runs, measure (see section 7).

**Also verify here — these could not be checked without the server:**

1. **The Isabelle download.** `curl -fL -o /dev/null <archive_url>` from the server before starting
   the build, and pick a different mirror from section 4a if that one is slow or blocked.
2. **The Solr image version.** `compose.yaml` pins `solr:9.8.1`. Compare it against the Solr that
   the pinned Isabelle bundles (look for `Isabelle/contrib/solr-*` on the volume) and match the tag;
   a newer Solr can refuse an index written by an older Lucene.
3. **The Solr home layout.** The service serves `~/.isabelle/find_facts/solr` directly with
   `solr-foreground -s`. Confirm that the directory the indexer produces is a valid Solr home with a
   core named `local`, and that the `user: "0:0"` in `compose.yaml` really is the uid that owns it.
4. **Shared libraries.** `python:3.11-slim` may lack libraries the Isabelle build needs (fontconfig
   is the usual suspect). Add apt packages to the Dockerfile if the build complains.
5. **`find_facts_index` under 2025-2.** The `-A <afp>` flag and the indexing of definitional commands
   were exercised against a devel-era Isabelle. `build_definition_corpus` fails loudly with a rebuild
   hint if definitions are missing.

**Accept.** Build completes; the website answers a search; `python -m src.duplicates --newest 10`
produces a report; neither
process writes a file the other owns (check timestamps on `.cache/`, `artifacts/`, `chroma_storages/`
— `llm_output_cache.json` and `llm_output_cache_dedup.json` are expected to change, one per process).

### Task 7 — Production config and full build (needs the server)

**Do.** Set `"isabelle_sessions": ["all"]` and confirm the LLM and embedding server URLs are
reachable from inside the container. The paths need no change: every relative path in `config.json`
resolves under `/app`, whose state directories are symlinks onto the volume. Then run
`python3 -m src.corpus` and let it run.

**Accept.** `python3 -m src.duplicates --newest 10` produces a report whose self-retrieval
control passes (the run exits non-zero if more than 5 % of documents fail to retrieve themselves).

### Task 8 — Service management and exposure (needs the server)

**Do.** systemd units wrapping `docker compose` (or the equivalent) and a reverse proxy with TLS in
front of `api_port`. Ordering and restart policy are already in `compose.yaml` (`depends_on` with a
Solr healthcheck, `restart: unless-stopped`), so the unit only has to bring compose up on boot.
`threads` stays at 1 — see section 5, item 1. Whatever supervises this must never start a second
`app` container: the LLM output cache it writes is not locked.

Hardening left undone on purpose: the containers run as root, which matches the previous behaviour
and is what lets the build container and Solr share one volume. Moving to a fixed non-root uid is
possible but has to be done for both at once.

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
`Ordinals_and_Cardinals` produced session databases but no heaps), session databases 2–5 GB, the
Isabelle distribution ~4 GB unpacked (contrib included — this was 10–15 GB while contrib was fetched
separately by `isabelle components -a`; the release archive bundles it), the AFP shallow clone
1–2 GB, Solr index 5–15 GB, ChromaDB ~8 GB, caches and artifacts ~4 GB. Total roughly **35–65 GB**,
so 500 GB is generous.

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

72 tests pass; the 7 errors from `tests/test_server_availability.py` are expected, it needs
`ISASEARCH_API_KEY` exported and the configured servers reachable. Formatting and linting:

```bash
nix shell nixpkgs#ruff -c ruff format src tests benchmark
```

`ruff check` currently reports 25 pre-existing findings across the codebase (26 before tasks 1–5);
keep that number from growing rather than trying to reach zero.
