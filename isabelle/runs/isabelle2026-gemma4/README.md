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
- `run.sh` builds the plain index, then the metadata index from the same session
  builds and FindFacts index. Logs go to `$ISASEARCH_HOME_USER/logs`.

Seed the description store once from the Python artifacts, with the plain
configuration:

```sh
isabelle isasearch_seed -c plain.json \
  artifacts/beaker_gemma4/document_descriptions.json \
  artifacts/beaker_gemma4/definition_descriptions.json
```

The full build takes days. Start it from a shell inside tmux (`tmux new-session -s
isasearch`), with `isabelle` on `PATH` and `ISASEARCH_API_KEY` exported:

```sh
./run.sh
```

A stopped run resumes when started again: built sessions, the FindFacts index and
stored descriptions and embeddings are reused.
