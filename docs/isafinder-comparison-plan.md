# Comparing IsaSearch with IsaFinder — autonomous testing plan

This is a work plan for a Claude session. Execute it phase by phase; each phase says
what it delivers and where it stops for a human decision. Report findings as you go.

## Context

IsaFinder (Qiyuan Xu, formerly also named "Isasearch") is a semantic search over the
Isabelle library and the AFP with the same architecture as this project — LLM
informalization → embedding → cosine retrieval — but a very different informalization:
a Claude/Codex *agent* (default `claude-opus-4-8[1m]`, ~$14,000 of API compute across a
mix of four frontier models) that reads the theory file and can query a live Isabelle
session over MCP, per *entity* (constants, theorems, types, classes, locales, bundles,
proof methods). Ours: a single prompt per source *block* to a local
gemma-4-26B-A4B-it-qat model at temperature 0, statement truncated at
`theorem_max_length` characters.

- Their code: https://github.com/xqyww123/Isabelle_Semantic_Embedding (clone it; the
  interpretation system prompt is in `Isabelle_Semantic_Embedding/semantic_interpretation.py`,
  the embedded-document convention in `document_text.py`, the LMDB access in `semantics.py`).
- Their data (Qiyuan explicitly offered it for this comparison):
  https://huggingface.co/datasets/ANTPG/MLML-data/blob/main/contrib/Semantic_Embedding/Isabelle_Semantic_Embedding.tar.zst
  (9.23 GB zst; LMDB databases: `semantics.lmdb` interpretations, `vector_<model>.lmdb` vectors).
  Their corpus snapshot is `afp-2026-05-13` + part of Isabelle/HOL 2025-2; ours is the
  afp-2025-2 mirror. Restrict every comparison to the intersection.
- Our benchmark: `benchmark/benchmark.csv` — ~90 rows, target identifiers are
  `entity_kname` values such as `Sqrt.sqrt_prime_irrational|thm` (qualified theorem
  names, so they should map nearly 1:1 to IsaFinder's entity names), three query
  columns (Title / Natural language / Noisy), metrics in `benchmark/metrics.py`
  (top-k accuracy, MRR, NDCG). NOTE: `benchmark/benchmark.py` boots the full corpus and
  needs Solr — do NOT use it for the standalone experiments below; write a standalone
  harness instead.
- Our descriptions artifact (`artifacts/beaker_gemma4/document_descriptions.json`) is
  produced on the server (bunsen) and the full-AFP run may still be in progress. What
  exists locally may be nothing or a subset — discover, don't assume.

The question that matters: **how much retrieval quality does $14k of agentic frontier
informalization buy over a $0 local model** — measured with everything else held equal.

## Guardrails

- The 9.23 GB download and the extracted LMDBs go OUTSIDE the repo (or into a
  gitignored `comparison-data/` — add the gitignore entry first). Never commit data.
- Ask before starting the 9.23 GB download (check `df -h` first).
- Commit scripts, mapping tables and reports (small ones) under `comparison/`.
- Do not present model-generated quality judgments as human ratings; qualitative
  comparisons must quote the actual texts side by side.

## Phase 0 — environment discovery (autonomous, ~minutes)

Determine and report: which machine this is; whether `.venv` works; whether `lmdb` and
`zstandard` are installable into it; free disk; whether the GPU embedding server
(`openai_embedding_base_url` in config.json, private network) is reachable; which of
our artifacts exist locally (`artifacts/`, `.cache/document_index.json`). Then ask for
the download go-ahead.

## Phase 1 — their data, opened and profiled (autonomous, ~hours incl. download)

Download, decompress, open the LMDBs using their repo's `semantics.py` as the schema
reference. Deliver a profile report: entity counts by kind; how many AFP entries are
covered; interpretation length distribution; whether records carry per-entity
provenance (which of the four models wrote which interpretation — methodologically
important, the Zulip thread suggests a mix); a dozen sample records verbatim.
Deliverable: `comparison/extract_isafinder.py` + `comparison/isafinder-profile.md`.

## Phase 2 — ID mapping and benchmark coverage (autonomous)

Map our benchmark's `entity_kname` targets (strip the `|thm` suffix; qualified name
remains) to their entity keys. Deliver: a mapping table for all benchmark targets,
found/missing counts, and — for targets their DB covers — their interpretation texts
dumped to `comparison/benchmark-targets-isafinder.json`. If our descriptions artifact
is available (locally or fetched later), produce the same dump for our side.
Deliverable: `comparison/target_mapping.csv` + coverage report.

## Phase 3 — qualitative side-by-side (autonomous once both sides exist)

For every benchmark target present in both corpora, and ~30 random mutual entities:
a two-column document (`comparison/side-by-side.md`) with their interpretation vs our
description, plus measured properties (length, mentions the canonical theorem name
y/n, formal-notation density). Where only their side exists yet, deliver their half
and flag the gap. No verdicts — the human does the blind reading.

## Phase 4 — same-embedder retrieval experiment (autonomous, CPU-only fallback)

The controlled experiment: hold the embedder, document format, and retrieval code
fixed; vary ONLY the description text.

- Pool: all mutual benchmark targets + ~5,000 mutual distractor entities.
- Embed two variants of the pool — (a) their interpretations, (b) our descriptions —
  with the SAME embedder: the GPU server's Qwen3-Embedding-4B if reachable, otherwise
  the local `sentence-transformers/multi-qa-distilbert-cos-v1` from config (CPU-fine
  at this scale; label results accordingly, the production embedder differs).
- Two ChromaDB collections, same document convention as `document_embedding_string`
  (description + source), same `embed` prompt.
- Run all three benchmark query columns against both; compute top-k/MRR/NDCG with
  `benchmark/metrics.py`; also run a query-refinement variant only if an LLM backend
  is reachable, else skip and say so.
- Caveat to print with every number: 5k distractors is not 380k; treat as
  preliminary/directional. Deliverable: `comparison/preliminary-results.md` + harness.

## Phase 5 — full-scale comparison (NOT autonomous — plan only)

Needs: our finished full-AFP corpus on bunsen, the production embedder, hours of
embedding for their ~full corpus, and a human blind evaluation of ~50 pairs from
Phase 3. Produce a concrete runbook for it based on what Phases 1–4 learned, including
the four-configuration benchmark run (ours/theirs × with/without query refinement)
and the cost/quality summary table for the writeup.

## Stop points

Ask the human before: the 9.23 GB download (Phase 1), anything requiring bunsen or
the GPU network, and before drawing any conclusion from Phase 4 numbers — they are
directional until Phase 5.
