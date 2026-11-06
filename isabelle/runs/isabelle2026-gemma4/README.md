# Isabelle2026 and AFP 2026 with Gemma 4

The plain index (without metadata) of all sessions (`all`: the AFP and the HOL
distribution without its documentation group), built from Isabelle2026 and a
Mercurial clone of `afp-2026` at the tag `Isabelle2026`. Documents are described
by `beaker_gemma4` and embedded by `Qwen3-Embedding-4B` on the TCS model servers,
with the sampling parameters of the earlier `beaker_gemma4` descriptions.

- `isabelle_timeout_scale: 3` keeps the slowest AFP sessions (`Munta_*`) within
  their timeouts with two parallel builds on 8 cores. `HOL-Metis_Examples` keys
  its read-only SMT certificates by the unscaled solver timeout and is built with
  `timeout_scale=1`.
- `embedding_reference_tolerance: 0.005` admits the stored vectors that came from
  the earlier index of this corpus: its definition vectors differ from the embedding
  server's current output by a relative squared error of 0.0017 to 0.0029 (cosine
  0.9985 or above), against 0.0004 to 0.0007 between two requests of the same text. A different model,
  pooling or preprocessing still fails the check at search start.
- The model servers' key is read from `$ISASEARCH_HOME_USER/api_key`, a private
  file (`chmod 600`) that is not part of the repository.

The stores on the server already hold the descriptions and embeddings of the
earlier deployment, so a build there reuses them; a build without them describes
and embeds every document.

Build the index. The full build takes days, so run it in tmux; its progress is
also logged to `$ISASEARCH_HOME_USER/logs`:

```sh
isabelle isasearch_index -c plain.json -i plain
```

A stopped build resumes when started again: built sessions, the FindFacts index
and stored descriptions and embeddings are reused.

## Automatic updates

`update` keeps the index current with the AFP 2026 and releases every new state of it
on GitHub. The registered AFP (`AFP_BASE`, a clean clone of `afp-2026`) moves to its
newest changeset, and the index is built again when the changesets since the last
build touch `thys` or `metadata`; changesets that touch only the website are recorded
without a build. A successful build removes the older generations (`isasearch_prune`).
The new generation is exported as it is (`isasearch_export`), compressed and split into parts below
GitHub's limit of 2 GiB per asset, and released as
`index-plain-DATE-afp-REVISION` on `FabianK-Dev/IsaSearch`, with the export's manifest
and `SHA256SUMS`, unless its data equals that of the last release. The release names
the commit of the component that built it, so the checkout must be pushed and without
local changes. Releases are kept.

Runs never overlap. A failed build is retried after 24 hours or as soon as the AFP
moves again; a failed release is retried by the next run, and its draft is deleted.
State lives in `$ISASEARCH_HOME_USER/update` (`built` and `released` are AFP
revisions); runs that do anything log to `$ISASEARCH_HOME_USER/logs/update-*.log`, next
to the logs of the builds. `update -f` builds even without new changesets. `update -o DIR`
packs the release as usual but writes its assets and notes to `DIR` instead of publishing
them, without a token and without touching the release state: a release to try out.

The release needs a GitHub token in `$ISASEARCH_HOME_USER/github_token` (`chmod 600`).
The repository belongs to another account, which fine-grained tokens cannot reach, so
it is a classic token with the `public_repo` scope of an account with push access.
Without it, `update` builds and skips the release. On the server, cron runs it every
hour; a run's own log has its output, and errors before that log starts (e.g. a failed
`hg pull`) go to `update-errors.log`:

```
PATH=/home/adm-mgrgh/.local/bin:/usr/local/bin:/usr/bin:/bin
17 * * * * /home/adm-mgrgh/IsaSearch-component/isabelle/runs/isabelle2026-gemma4/update > /dev/null 2>> /home/adm-mgrgh/.isabelle/Isabelle2026/isasearch/logs/update-errors.log
```

To use a release, download all parts, then unpack and install them:

```sh
cat isasearch-plain-*.tar.zst.* | zstd -d | tar -x
isabelle isasearch_import -f isasearch-plain -i plain
```

The parts hold the generation ready to search; the import checks its files against the
manifest and moves the directory into place. Measured on 2026-11-06 on the M2 Pro with the
generation of 2026-11-05 (5.7 GB): exporting took 5 s (copies, which APFS clones, and checksums), packing
7 s (5.0 GB in three parts, as for the interchange export), unpacking 6 s and installing 5 s,
against 36.5 minutes for importing the interchange export. The release of the server's
generation of the same day, with reference embeddings and packed by `update -f -o` (1 h 50 min
for the build, 5.3 GB in three parts), took 16 s to check against `SHA256SUMS`, 7 s to unpack
and 5 s to install on the M2 Pro; a first search then took 7 s, JVM and embedder start
included.

## Search on a laptop

The component's default configuration `etc/search.json` (option `isasearch_config`)
searches this index without a generative model. The searching tools start
llama.cpp's `llama-server` with the Q8_0 quantization of the official
`Qwen/Qwen3-Embedding-4B-GGUF` on the same machine, on the GPU if llama.cpp supports one
there and on the CPU otherwise. llama.cpp must be installed; the first start downloads the
model (4.3 GB) into llama.cpp's cache:

```sh
isabelle isasearch_server
```

At search start, and every 30 seconds in a server, the searching tools check the embedder
against the reference embeddings of the index: three short queries whose vectors the build
recorded with the embedder of the server. Indexes built before 2026-11-06 have none and are
checked by re-embedding two stored documents per corpus instead (up to 2,443 tokens here),
which the context of 4096 tokens has to hold; on the M2 Pro's CPU that added about 20 s to a
search, the reference embeddings well below one. To run an embedding server by hand instead,
replace `llamacpp_embedding_server` by `openai_embedding_base_url` and start it with the same
settings:

```sh
llama-server -hf Qwen/Qwen3-Embedding-4B-GGUF:Q8_0 --embedding --pooling last \
  --alias Qwen3-Embedding-4B -c 4096 -ub 4096 -np 1 --port 8080
```

Ollama was not measured; its `qwen3-embedding:4b` is Q4_K_M, so Q8_0 needs
`qwen3-embedding:4b-q8_0`.

## Query expansion on a laptop

The model servers expand queries with `beaker_gemma4`, the QAT Gemma 4 26B-A4B at
`UD-Q4_K_XL` (`gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` of `unsloth/gemma-4-26B-A4B-it-qat-GGUF`).
The default `etc/search.json` carries the same model as `llamacpp_query_server`, disabled;
with `"enabled": true` in a copy, searches start it on the first expanded query, with the
prompts of the index and the sampling parameters of `plain.json`.

Measured on 2026-11-06 on the M2 Pro (Metal) with eight benchmark queries: the first start
downloaded the model (14.2 GB) in under three minutes and loaded it in 11 s; an expansion then
took about 4 s. Sent the same requests, the local model and `beaker_gemma4` gave identical
expansions for two queries and expansions that agree in their first sentences for the other
six (temperature 0 on different hardware), and the expanded searches found the same first hit
for all eight and 9 or 10 of the same top 10. The running model occupied about 5.4 GB of
resident memory beside the embedder (0.5 GB) and the memory-mapped index.

Measured on 2026-11-05 against the generation of that day (389,754 theorems, 125,139
definitions), on an Apple M2 Pro with 32 GB and llama.cpp b11669 (nixpkgs `llama-cpp`
0.7.0), CPU-only (`-ngl 0 -t 8`) unless marked Metal, against the server embedder as
reference. Drift is the relative squared error of a fresh embedding against the stored
vector, for the two reference documents and 100 random ones per corpus, which is what
`embedding_reference_tolerance` bounds. The benchmark is `baseline` over the 259 queries of
`benchmark/benchmark.csv`; latency is the elapsed time per query.

| Embedder | Drift theorems, median / max | Drift definitions, median / max | Hit@10 | MRR | NDCG | Latency median / p90 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| server | 0.0014 / 0.0028 | 0.0018 / 0.0032 | 0.811 | 0.575 | 0.585 | 0.20 / 0.25 s |
| f16 | 0.0013 / 0.0027 | 0.0016 / 0.0030 | 0.811 | 0.577 | 0.586 | 1.29 / 3.03 s |
| Q8_0 | 0.0014 / 0.0031 | 0.0018 / 0.0032 | 0.811 | 0.577 | 0.586 | 0.51 / 0.79 s |
| Q8_0, Metal | | | 0.811 | 0.578 | 0.586 | 0.24 / 0.40 s |
| Q6_K | 0.0079 / 0.0135 | 0.0086 / 0.0167 | 0.811 | 0.563 | 0.580 | 0.75 / 1.06 s |
| Q4_K_M | 0.0317 / 0.0432 | 0.0332 / 0.0524 | 0.811 | 0.568 | 0.580 | 0.56 / 0.78 s |

- Every current embedder, the server included, differs from the stored vectors by a relative
  error of about 0.0015, because these came from an earlier deployment (see above). Q8_0
  adds nothing to that and passes the tolerance of 0.005; Q6_K and Q4_K_M exceed it with
  every document, although their rankings stay close to the server's.
- Q8_0 and f16 rank as the server does. f16 is slower than Q8_0 on the CPU, and the
  K-quants are not faster.
- With a context of 4096, llama-server occupies 4.8 GB with Q8_0 and 3.2 GB with Q4_K_M
  (physical footprint; the memory-mapped model file comes on top as reclaimable cache).
  With the index (5.7 GB, memory-mapped) and the JVM, a laptop needs 16 GB.
- Embedding a whole document takes 1.3 to 2.5 s on the CPU, so the reference check of an
  index without reference embeddings, which embeds two documents per corpus every 30
  seconds, adds seconds to a search.
- The machine was not idle during the later CPU runs; Q8_0 measured again with a context of
  4096 gave 0.62 / 1.62 s.
