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
