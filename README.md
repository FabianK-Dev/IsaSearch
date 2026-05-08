# IsaSearch

This repository provides an AI-assisted semantic theorem search for the Archive of Formal Proofs using sentence-transformers, ChromaDB and LLMs. Additionally, it contains our benchmark data and results.

## Requirements

- [Python](https://www.python.org/downloads/) 3.11.2 or higher
- [pip](https://pip.pypa.io/en/stable/installation/) 23.0.1 or higher
- [git](https://git-scm.com/downloads) 2.47.3 or higher
- [Docker](https://www.docker.com/get-started) 29.2.1 or higher
- [Ollama](https://ollama.com/download)

## Setup

### Quickstart

> ⚠️ **Warning:** Please run the following commands **inside the root folder of the repository** (this is necessary to ensure files like `config.json` are loaded correctly):

```bash
python3 -m venv .venv  # If this command does not work, please install the `venv` module for Python: `pip install venv`
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
python3 -m src.app
```

The application starts Ollama automatically and pulls the configured models if they are missing.

**Note on Indexing Time:**
Building the full FindFacts index for the entire Archive of Formal Proofs takes about 24 hours, informalizing all theorems ~25 hours, and embedding them into ChromaDB ~2 hours.

**Default Test Configuration:**
> ⚠️ **Warning:** To allow for immediate testing, the default `config.json` is restricted to only two sessions:

```json
"isabelle_sessions": ["Ramsey-Infinite", "Ordinals_and_Cardinals"]
```

If you want to search the entire AFP, you need to update the `isabelle_sessions` list in `config.json` to include all desired sessions (or use `["all"]` if supported by your setup), but be prepared for the significant processing time mentioned above.

### Benchmark

To run the Benchmark, use `python3 -m benchmark.benchmark` inside the root folder of the repository. If you want to run a full benchmark that compares different strategies (as discussed in our paper), run `run_full_benchmark.sh`.

**Important:** The results generated with the default configuration will differ from the paper. This is because the test setup only indexes the two sessions mentioned above (`"Ramsey-Infinite"`, `"Ordinals_and_Cardinals"`), whereas the paper results are based on the complete Archive of Formal Proofs.

## Screenshot

Below you can find a screenshot of the web UI:

## Pre-Commit hooks

This project uses [ruff](https://pypi.org/project/ruff/) and other pre-commit hooks to maintain code quality.

When continuing development, please install the hooks:

```bash
pre-commit install
```
