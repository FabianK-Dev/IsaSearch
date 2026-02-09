# IsaSearch

This repository provides an AI-assisted semantic theorem search for the Archive of Formal Proofs using sentence-transformers, ChromaDB and LLMs. Additionally, it contains our benchmark data and results.

## Requirements

- [Python](https://www.python.org/downloads/) 3.11.2 or higher
- [pip](https://pip.pypa.io/en/stable/installation/) 23.0.1 or higher
- [git](https://git-scm.com/downloads) 2.47.3 or higher
- [Docker](https://www.docker.com/get-started) 29.2.1 or higher

**If you want to run this application using the GPU (optional but recommended):**
- a GPU with at least 12 GB VRAM (NVIDIA, AMD and Intel GPUs are supported)

## Setup

### Quickstart

> ⚠️ **Warning:** Please run the following commands **inside the root folder of the repository** (this is necessary to ensure files like `config.json` are loaded correctly):

```bash
python3 -m venv .venv  # If this command does not work, please install the `venv` module for Python: `pip install venv`
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m src.app
```

Embedding all theorems into the ChromaDB collection takes about 2 hours, building the FindFacts index with all sessions of the Archive of Formal proofs about 24 hours and informalizing all theorems about 25 hours. As a result, for testing purposes we have only enabled two sessions (`"Ramsey-Infinite", "Ordinals_and_Cardinals"`) to be indexed.

### Benchmark

To run the Benchmark, use `python3 -m benchmark.benchmark` inside the root folder of the repository. If you want to run a full benchmark that compares different strategies that are also compared in our paper, run `run_full_benchmark.sh`.

Please keep in mind that the results will be different from the ones in the paper, as we have only enabled two sessions (`"Ramsey-Infinite", "Ordinals_and_Cardinals"`) to be indexed for testing purposes, while in the paper we have indexed all sessions of the Archive of Formal Proofs.

## Screenshot

Below you can find a screenshot of the web UI:

![Screenshot of the web UI](paper/latex/website_screenshot.jpg)

## Pre-Commit hooks

This project uses [ruff](https://pypi.org/project/ruff/) and other pre-commit hooks from the [pre-commit/pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks) (licensed under the MIT License) repository, which are configured in the `.pre-commit-config.yaml` to follow formatting and linting standards and best practices.

When continuing development, I suggest installing `pre-commits` first:
```bash
pre-commit install
```
