Previous: `benchmark/results/UR_microsoft-Phi-3.5-mini-instruct_Phi-3-mini-4k-instruct.Q4_0.gguf.json`

Current: `benchmark/results/20260916T112455.618611Z_UR`

# Benchmark comparison

Evaluated queries: previous **255**, current **259**; matched by target, query type and exact input text, excluding known label changes: **255**.

The table recomputes both means on those matched queries. Deltas are current minus previous; positive is better.

| Query type | N | Metric | Previous | Current | Delta |
| --- | ---: | --- | ---: | ---: | ---: |
| All queries | 255 | Hit@10 | 0.7725 | 0.8627 | +0.0902 |
| All queries | 255 | MRR | 0.5463 | 0.6128 | +0.0665 |
| All queries | 255 | NDCG | 0.5577 | 0.5994 | +0.0417 |
| Natural language query | 85 | Hit@10 | 0.8235 | 0.8706 | +0.0471 |
| Natural language query | 85 | MRR | 0.5659 | 0.6172 | +0.0514 |
| Natural language query | 85 | NDCG | 0.5910 | 0.6145 | +0.0235 |
| Noisy natural language query | 85 | Hit@10 | 0.6588 | 0.8000 | +0.1412 |
| Noisy natural language query | 85 | MRR | 0.4531 | 0.5732 | +0.1201 |
| Noisy natural language query | 85 | NDCG | 0.4722 | 0.5714 | +0.0992 |
| Title query | 85 | Hit@10 | 0.8353 | 0.9176 | +0.0824 |
| Title query | 85 | MRR | 0.6199 | 0.6480 | +0.0281 |
| Title query | 85 | NDCG | 0.6100 | 0.6123 | +0.0023 |

Only in previous: 0.

Only in current: 4.
- cramers-rule / Natural language query
- cramers-rule / Title query
- rational-approximation-via-pells-equation / Natural language query
- rational-approximation-via-pells-equation / Title query

Changed input text (excluded): 0.

Changed relevance labels (excluded): 0.

Previous skipped targets:
- target_document_not_found: 2
- target_identifier_missing: 7

Current skipped targets:
- target_document_not_found: 1
- target_identifier_missing: 7

Current skipped individual queries:
- cramers-rule / Noisy natural language query: paper_noisy_query_missing
- rational-approximation-via-pells-equation / Noisy natural language query: paper_noisy_query_missing

Largest RR regressions:
- polyhedron-formula / Noisy natural language query: -1.0000
- taylors-theorem / Noisy natural language query: -0.9714
- the-binomial-theorem / Noisy natural language query: -0.9688
- the-solution-of-the-general-quartic-equation / Title query: -0.9091
- bezouts-theorem / Title query: -0.8889
- gödels-incompleteness-theorem-1 / Title query: -0.8333
- prime-number-theorem / Title query: -0.8000
- the-number-of-subsets-of-a-set / Title query: -0.8000
- the-solution-of-a-cubic / Natural language query: -0.8000
- fundamental-theorem-of-integral-calculus / Natural language query: -0.7500

Largest RR improvements:
- wilsons-theorem / Natural language query: +1.0000
- the-friendship-theorem / Title query: +1.0000
- the-factor-and-remainder-theorems / Title query: +1.0000
- the-birthday-problem / Title query: +1.0000
- the-birthday-problem / Noisy natural language query: +1.0000
- the-birthday-problem / Natural language query: +1.0000
- ptolemys-theorem / Noisy natural language query: +1.0000
- lhôpitals-rule / Noisy natural language query: +1.0000
- dissection-of-cubes-j.e.-littlewoods-elegant-proof / Noisy natural language query: +1.0000
- desarguess-theorem / Natural language query: +1.0000

Legacy results do not record relevance labels, so label equality cannot be verified for those runs. Matching queries does not control for corpus contents, models or prompts. Check the run manifests. Timing is omitted because cached durations and different hardware are not directly comparable.
