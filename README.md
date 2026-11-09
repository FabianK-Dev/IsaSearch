# IsaSearch

AI-assisted semantic search for the theorems and definitions of the Archive of
Formal Proofs and the Isabelle distribution. An LLM describes every document,
the descriptions are embedded, and queries are answered by nearest-neighbour
search. Around the search there is a website, an HTTP API, a duplicate analysis
for AFP entries and the benchmark of the [paper](https://files.sketis.net/Isabelle_Workshop_2026/Isabelle_2026_paper8.pdf).

The details are in this [paper](https://files.sketis.net/Isabelle_Workshop_2026/Isabelle_2026_paper8.pdf) (Isabelle Workshop 2026).

To search on your own machine, follow the [quickstart](QUICKSTART.md).

Everything is implemented as an Isabelle2026 component in [`isabelle`](isabelle);
[its README](isabelle/README.md) covers registration, configuration, building and
serving an index, duplicate analysis and the benchmarks.

| Path | Content |
| --- | --- |
| [`isabelle`](isabelle) | the Isabelle component |
| [`pide_ai`](pide_ai) | the search as a tool of [PIDE AI](https://github.com/kappelmann/isabelle-pide-ai), with an agent skill |
| [`reports`](reports) | duplicate analysis of the ten newest AFP entries (2026-09-16) |
