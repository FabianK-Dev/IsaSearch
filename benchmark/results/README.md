# Paper benchmark baselines

The six flat JSON files in this directory are the original per-query results for
*AI-assisted theorem search in Isabelle*. They are tracked in Git and can be passed
directly to `python3 -m benchmark.compare`. No separate paper checkout is needed to
run a comparison.

| Strategy | Query | Metadata | Result file |
| --- | --- | --- | --- |
| baseline | Original | No | [baseline](baseline_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| R | Expanded | No | [R](R_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| UR | Original + expanded | No | [UR](UR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| M | Original | Yes | [M](M_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| MR | Expanded | Yes | [MR](MR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |
| MUR | Original + expanded | Yes | [MUR](MUR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json) |

Each baseline evaluates 85 targets with three query types, totaling 255 queries.
The result files contain individual queries and metrics as well as summaries, so
the comparison can account for changed coverage and noisy-query text.
The benchmark replays the UR file's saved noisy inputs for all strategies, checking
its hash against the index below. All six historical files use the same query inputs.
Keep these files available on the server when rerunning the benchmark.

From the repository root, compare a new UR run with the matching paper baseline
(replace `RUN_DIRECTORY` with the path printed by the benchmark or archive command):

```bash
python3 -m benchmark.compare \
  benchmark/results/UR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json \
  RUN_DIRECTORY
```

The second argument can also be a legacy result JSON, such as
`benchmark/results/UR_beaker_gemma4_beaker_gemma4.json`.

## Verification and provenance

[paper-baselines.json](paper-baselines.json) identifies the six files by SHA-256
and records the paper source revision used to verify them:

- Repository: `ai-assisted-theorem-search-in-isabelle`
- Commit: `0b456d06dd7a4630549162a6bdaf56b285480938`
- Source: `paper/AFP-AI-search.tex`, table `tab:suchstrategien_tabelle`

All 96 retrieval values (Hit@10, NDCG, mean reciprocal rank and mean rank, across
four query groups and six strategies) match the paper's three-decimal rounding.
Some timing values differ, notably for UR, so the JSON durations should not be
treated as an exact transcription of the published timing column. The comparison
command omits timing.

These are historical results without a contemporaneous run manifest. The paper
revision above verifies the published table; it is not the revision of the code
or corpus used for the original experiment. Those exact historical revisions and
the complete runtime configuration are unknown here. The index records that
limitation instead of assigning today's configuration to the old runs.

Keep these baseline JSON files unchanged. New runs belong in their own timestamped
directories with `results.json` and `manifest.json` as described in the main README.
