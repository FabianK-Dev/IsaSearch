# To-do

## AI search
- [x] Choose specific model via config
- [ ] CPU vs. GPU: add error handling

## Benchmark
- [x] Maybe use Freek Wiedijk's 100 Theore  ms list (Wiedijk, F.: Formalizing 100 theorems, https://www.cs.ru.nl/~freek/100/) (of which about 90 are implemented in the AFP)
- [x] List of models to compare via config
- [x] ~~Compare with/without stopwords removal, URL removal, non-letter removal (e.g. remove symbols), number removal, ...~~
- Response time
- Precision@k (e.g. k=10)
- Recall@k
- F1-Score
- Average Precision
- Mean Average Precision
- Discounted cumulative gain
- Mean Reciprocal Rank
- Normalized Discounted Cumulative Gain?

### Comparisons
- one model: microsoft/Phi-3.5-mini-instruct (1)
- with / without metadata + title (2)
- with / without LLM query refinement (2)
- comparison: bi-encoder + cross-encoder (1)
- maybe: original query + refined query ? (2)
- total: 1*2*2 + 1 = 5 runs

## Deployment
- [ ] FastAPI
- [ ] UI with HTML (choose framework later)

## Optional
- [ ] Docker image
- [ ] Pytests

# Paper
- How to interpret the Score?
- Average score?
- CPU vs. GPU?
