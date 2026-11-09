# IsaSearch

Semantic search for the theorems and definitions of the Archive of Formal Proofs and the
Isabelle distribution. An LLM describes every theorem and definition, the descriptions are
embedded, and a query returns the nearest descriptions. IsaSearch also has a website, an HTTP
API, a duplicate analysis for AFP entries and the benchmark of the
[paper](https://files.sketis.net/Isabelle_Workshop_2026/Isabelle_2026_paper8.pdf) (Isabelle
Workshop 2026).

To search on your own machine, follow the [quickstart](QUICKSTART.md).

| Path | Content |
| --- | --- |
| [`isabelle`](isabelle) | the Isabelle2026 component: search, website, index builds, duplicates, benchmarks ([README](isabelle/README.md)) |
| [`pide_ai`](pide_ai) | the search as a tool of [PIDE AI](https://github.com/kappelmann/isabelle-pide-ai), with an agent skill |
| [`reports`](reports) | duplicate analysis of the ten newest AFP entries (2026-09-16) |
