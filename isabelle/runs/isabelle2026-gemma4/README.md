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

## Search on a laptop

`laptop.json` searches this index without a generative model. The searching tools start
llama.cpp's `llama-server` with the Q8_0 quantization of the official
`Qwen/Qwen3-Embedding-4B-GGUF` on the same machine, on the GPU if llama.cpp supports one
there and on the CPU otherwise. llama.cpp must be installed; the first start downloads the
model (4.3 GB) into llama.cpp's cache:

```sh
isabelle isasearch_server -c laptop.json -i plain
```

The context of one slot of 4096 tokens holds the inputs of the reference check at search
start, which re-embeds stored documents (up to 2,443 tokens here). To run an embedding
server by hand instead, replace `llamacpp_embedding_server` by `openai_embedding_base_url`
and start it with the same settings:

```sh
llama-server -hf Qwen/Qwen3-Embedding-4B-GGUF:Q8_0 --embedding --pooling last \
  --alias Qwen3-Embedding-4B -c 4096 -ub 4096 -np 1 --port 8080
```

Ollama was not measured; its `qwen3-embedding:4b` is Q4_K_M, so Q8_0 needs
`qwen3-embedding:4b-q8_0`.

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
- Embedding a whole document takes 1.3 to 2.5 s on the CPU, so the reference check, which
  embeds two documents per corpus every 30 seconds, adds seconds to a search.
- The machine was not idle during the later CPU runs; Q8_0 measured again with a context of
  4096 gave 0.62 / 1.62 s.
