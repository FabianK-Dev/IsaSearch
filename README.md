# IsaSearch

AI-assisted semantic search for the theorems and definitions of the Archive of
Formal Proofs and the Isabelle distribution. An LLM describes every document,
the descriptions are embedded, and queries are answered by nearest-neighbour
search. Around the search there is a website, an HTTP API, a duplicate analysis
for AFP entries and the benchmark of the paper.

To search on your own machine, follow the [quickstart](QUICKSTART.md).

Everything is implemented as an Isabelle2026 component in [`isabelle`](isabelle);
[its README](isabelle/README.md) covers registration, configuration, building and
serving an index, duplicate analysis and the benchmarks.

| Path | Content |
| --- | --- |
| [`isabelle`](isabelle) | the Isabelle component |
| [`pide_ai`](pide_ai) | the search as a tool of [PIDE AI](https://github.com/kappelmann/isabelle-pide-ai), with an agent skill |
| [`paper`](paper) | LaTeX sources of the paper |
| [`reports`](reports) | duplicate analysis of the ten newest AFP entries (2026-09-16) |
| [`todo.md`](todo.md) | open work |
| [`isabelle-pide-exports-race.md`](isabelle-pide-exports-race.md) | report on an Isabelle2026 build race that loses the PIDE exports of a session |
