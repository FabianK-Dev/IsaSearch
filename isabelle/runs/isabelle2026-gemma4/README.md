# Isabelle2026 and AFP 2026 with Gemma 4

The released `plain` index (without metadata) of all sessions (`all`: the AFP and the HOL
distribution without its documentation group), built from Isabelle2026 and a Mercurial clone of
`afp-2026`. Documents are described by `beaker_gemma4` and embedded by `Qwen3-Embedding-4B` on
the TCS model servers ([`plain.json`](plain.json)).

- `isabelle_timeout_scale: 3` keeps the slowest AFP sessions (`Munta_*`) within their timeouts
  with two parallel builds on 8 cores. `HOL-Metis_Examples` keys its SMT certificates by the
  unscaled solver timeout and is built with `timeout_scale=1`.
- `embedding_reference_tolerance: 0.005` admits the stored vectors from the earlier index of
  this corpus: they differ from the current embedder's output by a relative squared error of
  0.0017 to 0.0029 (cosine ≥ 0.9985), against 0.0004 to 0.0007 between two requests of the same
  text. A different model, pooling or preprocessing still fails the check.
- The model servers' key is read from `$ISASEARCH_HOME_USER/api_key` (`chmod 600`).

## Build

```sh
isabelle isasearch_index -c plain.json -i plain
```

A build from scratch takes days, so run it in tmux; progress is also logged to
`$ISASEARCH_HOME_USER/logs`. A stopped build resumes with the built sessions, the FindFacts
index and the stored descriptions and embeddings. The stores on the server hold those of the
earlier deployment, so a build there only describes new documents.

## Automatic updates and releases

[`update`](update) keeps the index current with the AFP 2026, analyses new entries for
duplicates, and releases every new state on GitHub (option `isasearch_releases`):

1. It pulls the registered AFP (`AFP_BASE`, a clean clone of `afp-2026`) and updates it to the
   newest changeset. If the changesets since the last build touch `thys` or `metadata`, it
   builds the index again and prunes the older generations; otherwise it only records the
   revision.
2. After a build, it runs `isasearch_duplicates -k all` on the entries that the changesets
   added (each adds `metadata/entries/ENTRY.toml`), against the new index and with the LLM
   judge of `plain.json`. The report goes to `$ISASEARCH_HOME_USER/update/duplicates/REVISION`.
   Entries whose sessions failed to build are listed as not in the index.
3. It exports the new generation (`isasearch_export`), compresses it with zstd, splits it into
   parts below GitHub's 2 GiB limit, and publishes them as release
   `index-plain-DATE-afp-REVISION` with the manifest, `SHA256SUMS` and notes, unless the data
   equals that of the last release. The release names the component commit that built it, so
   the checkout must be pushed and clean. The duplicate analysis of the revision is part of
   the release: the reports `duplicates-afp-REVISION.json`, `_near-exact.md` and
   `_possible.md`, and a table per entry in the notes.

`isasearch_import` relies on this layout: it matches `REVISION` against the user's AFP and
installs the parts.

Runs never overlap. A failed build is retried after 24 hours or when the AFP moves again; a
failed release is retried by the next run and its draft deleted. A failed duplicate analysis
does not hold up the release: it is retried after 24 hours or with the next build, and a
later report is attached to the release of its revision, replacing an earlier one. State lives
in `$ISASEARCH_HOME_USER/update` (`built` and `released` are AFP revisions,
`duplicates_pending` the entries still to analyse); runs that do something log to
`$ISASEARCH_HOME_USER/logs/update-*.log`.

- `update -f` builds even without new changesets.
- `update -e ENTRY` (repeatable) analyses ENTRY as well, together with the entries already
  analysed for the revision, e.g. to analyse an entry again.
- `update -o DIR` writes the assets and notes to `DIR` instead of publishing them, without a
  token and without touching the release state.

Cron runs it hourly on the server; errors before a run's log starts (e.g. a failed `hg pull`)
go to `update-errors.log`:

```
PATH=/home/adm-mgrgh/.local/bin:/usr/local/bin:/usr/bin:/bin
17 * * * * /home/adm-mgrgh/IsaSearch-component/isabelle/runs/isabelle2026-gemma4/update > /dev/null 2>> /home/adm-mgrgh/.isabelle/Isabelle2026/isasearch/logs/update-errors.log
```

## Server setup

On a Linux machine with access to the model servers:

1. Install Isabelle2026 with `isabelle` on the cron `PATH`, and `hg`, `git`, `python3`, `zstd`,
   `curl` and GNU coreutils (`flock`, `split`, `sha256sum`).
2. Clone `afp-2026` (see the component README, "Provenance") and this repository, and register
   both: `isabelle components -u AFP` and `isabelle components -u REPOSITORY/isabelle`.
3. In `$ISABELLE_HOME_USER/etc/settings`, raise the JVM limits:
   `ISABELLE_TOOL_JAVA_OPTIONS="-Djava.awt.headless=true -Xms2g -Xmx24g -Xss128m"`.
4. Put the model servers' key in `$ISASEARCH_HOME_USER/api_key` and a GitHub token in
   `$ISASEARCH_HOME_USER/github_token` (both `chmod 600`). The repository belongs to another
   account, which fine-grained tokens cannot reach, so it is a classic token with the
   `public_repo` scope of an account with push access. Without it, `update` builds and skips
   the release.
5. Run the first build by hand (above), or copy the stores `llm_cache` and `embeddings` from
   `$ISASEARCH_HOME_USER` of the old server to skip describing everything again.
6. Install the cron job above.

## Laptop measurements

All on an Apple M2 Pro with 32 GB.

**Installing a release** (2026-11-06, 5.7 GB generation, 5.0 GB in three parts): checking
`SHA256SUMS` took 16 s, unpacking 7 s and installing 5 s; the first search then took 7 s, JVM
and embedder start included. Importing the interchange export instead took 36.5 minutes.

**Query embedder** (2026-11-05, 389,754 theorems and 125,139 definitions, llama.cpp b11669,
CPU-only with `-ngl 0 -t 8` unless marked Metal). Drift is the relative squared error of a fresh
embedding against the stored vector, over the two reference documents and 100 random ones per
corpus, which `embedding_reference_tolerance` bounds. The benchmark is `baseline` over the 259
queries of `benchmark/benchmark.csv`; latency is per query.

| Embedder | Drift theorems, median / max | Drift definitions, median / max | Hit@10 | MRR | NDCG | Latency median / p90 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| server | 0.0014 / 0.0028 | 0.0018 / 0.0032 | 0.811 | 0.575 | 0.585 | 0.20 / 0.25 s |
| f16 | 0.0013 / 0.0027 | 0.0016 / 0.0030 | 0.811 | 0.577 | 0.586 | 1.29 / 3.03 s |
| Q8_0 | 0.0014 / 0.0031 | 0.0018 / 0.0032 | 0.811 | 0.577 | 0.586 | 0.51 / 0.79 s |
| Q8_0, Metal | | | 0.811 | 0.578 | 0.586 | 0.24 / 0.40 s |
| Q6_K | 0.0079 / 0.0135 | 0.0086 / 0.0167 | 0.811 | 0.563 | 0.580 | 0.75 / 1.06 s |
| Q4_K_M | 0.0317 / 0.0432 | 0.0332 / 0.0524 | 0.811 | 0.568 | 0.580 | 0.56 / 0.78 s |

- Every embedder, the server's included, drifts by about 0.0015 from the stored vectors, which
  came from an earlier deployment. Q8_0 adds nothing and passes the tolerance of 0.005; Q6_K
  and Q4_K_M exceed it, although their rankings stay close. Q8_0 is the default.
- f16 ranks like Q8_0 but is slower on the CPU; the K-quants are not faster.
- With a context of 4096, llama-server takes 4.8 GB with Q8_0 (3.2 GB with Q4_K_M). With the
  memory-mapped index (5.7 GB) and the JVM, a laptop needs 16 GB.
- Searches check the embedder against three short reference queries recorded by the build,
  at search start and every 30 s in a server. Indexes built before 2026-11-06 have none and
  re-embed two documents per corpus instead (up to 2,443 tokens), which added about 20 s to a
  search on the CPU.
- Ollama was not measured; its `qwen3-embedding:4b` is Q4_K_M, so Q8_0 needs
  `qwen3-embedding:4b-q8_0`.

To run the embedder by hand, replace `llamacpp_embedding_server` by
`openai_embedding_base_url` and start it with the same settings:

```sh
llama-server -hf Qwen/Qwen3-Embedding-4B-GGUF:Q8_0 --embedding --pooling last \
  --alias Qwen3-Embedding-4B -c 4096 -ub 4096 -np 1 --port 8080
```

**Query expansion** (2026-11-06, Metal, eight benchmark queries) with the model of
`llamacpp_query_server` in `etc/search.json`, the QAT Gemma 4 26B-A4B at `UD-Q4_K_XL` that the
server runs as `beaker_gemma4`: the first start downloaded 14.2 GB in under three minutes and
loaded it in 11 s; an expansion then took about 4 s and the model kept about 5.4 GB resident.
Its expansions matched the server's for two queries and agreed in their first sentences for
the other six (temperature 0 on different hardware); the expanded searches had the same first
hit for all eight and 9 or 10 of the same top 10.
