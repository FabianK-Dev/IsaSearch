# Isabelle2026 and AFP 2026 with Gemma 4

The plain and metadata indexes of all sessions (`all`: the AFP and the HOL
distribution without its documentation group), built from Isabelle2026 and a
Mercurial clone of `afp-2026` at the tag `Isabelle2026`. Documents are described
by `beaker_gemma4` and embedded by `Qwen3-Embedding-4B` on the TCS model servers,
with the sampling parameters of the Python artifacts `artifacts/beaker_gemma4`.

- `plain.json` and `metadata.json` differ only in `add_metadata`.
- `isabelle_timeout_scale: 3` keeps the slowest AFP sessions (`Munta_*`) within
  their timeouts with two parallel builds on 8 cores. `HOL-Metis_Examples` keys
  its read-only SMT certificates by the unscaled solver timeout and is built with
  `timeout_scale=1`.
- The model servers' key is read from `$ISASEARCH_HOME_USER/api_key`, a private
  file (`chmod 600`) that is not part of the repository.

Seed the description store once from the Python artifacts:

```sh
isabelle isasearch_seed -c plain.json \
  artifacts/beaker_gemma4/document_descriptions.json \
  artifacts/beaker_gemma4/definition_descriptions.json
```

Build both indexes from one session build. The full build takes days, so run it
in tmux; its progress is also logged to `$ISASEARCH_HOME_USER/logs`:

```sh
isabelle isasearch_index -c plain.json -i plain -c metadata.json -i metadata
```

A stopped build resumes when started again: built sessions, the FindFacts index
and stored descriptions and embeddings are reused.
