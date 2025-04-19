# To-do

# AFP downloader
- [ ] Repository downloader (if does not already exist)
- [ ] Choose specific version, branch, commit or devel via config
- [x] AFP loader

## Parser
- [ ] LaTeX parser
- [x] RegEx parser
- [ ] FindFacts with build_importer

## AI search
- [ ] Choose specific model via config
- [ ] CPU vs. GPU: add error handling

## Benchmark
- [ ] Maybe use Freek Wiedijk's 100 Theore  ms list (Wiedijk, F.: Formalizing 100 theorems, https://www.cs.ru.nl/~freek/100/) (of which about 90 are implemented in the AFP)
- [ ] List of models to compare via config
- [ ] Compare with/without stopwords removal, URL removal, non-letter removal (e.g. remove symbols), number removal, ...

## Deployment
- [ ] FastAPI
- [ ] UI with HTML (choose framework later)

## Optional
- [ ] Docker image
- [ ] Pytests

# Benchmark
- Response time
- ~~Precision@k (e.g. k=10)~~
- ~~Recall@k~~
- ~~F1-Score~~
- ~~Average Precision~~
- ~~Mean Average Precision~~
- Discounted cumulative gain
- Mean Reciprocal Rank
- Normalized Discounted Cumulative Gain?

# Paper
- How to interpret the Score?
- Average score?
- CPU vs. GPU? => 
