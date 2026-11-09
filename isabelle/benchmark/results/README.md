# Paper benchmark baselines

The six JSON files here are the original per-query results of *AI-assisted theorem search in
Isabelle*. `isabelle isasearch_compare` reads them directly.

| Strategy | Query | Metadata | Result file |
| --- | --- | --- | --- |
| baseline | original | no | [baseline](baseline_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| R | expanded | no | [R](R_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| UR | original + expanded | no | [UR](UR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| M | original | yes | [M](M_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| MR | expanded | yes | [MR](MR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| MUR | original + expanded | yes | [MUR](MUR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |

Each file evaluates 85 targets with three query types (255 queries) and holds the individual
queries, their metrics and summaries. All six use the same query inputs; the benchmark replays
those of the UR file, checking its hash. Keep these files unchanged.

Compare a new run with a baseline, from the repository root (`RUN_DIRECTORY` is the strategy
directory the benchmark prints, or a result file):

```sh
isabelle isasearch_compare \
  isabelle/benchmark/results/UR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json \
  RUN_DIRECTORY
```

## Provenance

[`paper-baselines.json`](paper-baselines.json) identifies the six files by SHA-256 and records
the paper revision that verifies them: repository `ai-assisted-theorem-search-in-isabelle`,
commit `0b456d06dd7a4630549162a6bdaf56b285480938`, table `tab:suchstrategien_tabelle` of
`paper/AFP-AI-search.tex`.

All 96 retrieval values (Hit@10, NDCG, mean reciprocal rank and mean rank, for four query
groups and six strategies) match the paper's three-decimal rounding. Some timings differ,
notably for UR, so the durations are not an exact transcription of the published timing
column; the comparison omits timing. The code, corpus and configuration of the original runs
are unknown; the paper revision verifies only the published table.
