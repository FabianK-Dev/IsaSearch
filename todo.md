# To-do

## AI search
- [x] Choose specific model via config
- [ ] CPU vs. GPU: add error handling

## Benchmark
- [x] Maybe use Freek Wiedijk's 100 Theore  ms list (Wiedijk, F.: Formalizing 100 theorems, https://www.cs.ru.nl/~freek/100/) (of which about 90 are implemented in the AFP)
- [x] List of models to compare via config
- [x] Response time
- [ ] Search query: more difficulty version of Natural Language Query
- Precision@k (e.g. k=10)
- Recall@k
- F1-Score
- [x] ~~Average Precision~~
- [x] ~~Mean Average Precision~~
- [x] Discounted cumulative gain
- [x] Mean Reciprocal Rank
- [x] Normalized Discounted Cumulative Gain?

### Comparisons
- one model: microsoft/Phi-3.5-mini-instruct (1)
- [x] with / without metadata + title (*2)
- [x] with / without LLM query refinement (*2)
- [x] hybrid: original query + refined query ? (+1)
- [x] ~~comparison: bi-encoder + cross-encoder (1)~~
- total: 1*2*2 + 1 = 5 runs

## Deployment
- [ ] FastAPI
- [ ] UI with React

## Optional
- [x] Docker image
- [x] ~~Pytests~~
- [ ] Warning threshold
- [ ] Handle bad LLM refinements or <BEGIN>false<END>

# Paper
- How to interpret the Score?
- Average score?
- CPU vs. GPU?
