# AFP AI Search

>An AI-assisted semantic theorem finder for the Archive of Formal Proofs using sentence-transformers, ChromaDB and LLMs.

## Requirements

- [Python](https://www.python.org/downloads/) 3.11.2 or higher
- [pip](https://pip.pypa.io/en/stable/installation/) 23.0.1 or higher
- [Docker](https://docs.docker.com/engine/install/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

**If you want to run this application using the GPU (highly recommended):**
- a NVIDIA GPU with at least 12 GB VRAM that supports CUDA (e.g. a NVIDIA GeForce RTX 4070)
- [NVIDIA drivers](https://www.nvidia.com/en-us/drivers/) that are compatible with CUDA version 12.8 (e.g. NVIDIA driver version 570.153.02)

## Setup

There are multiple ways to set up the application, of which I recommend the usage of Docker because it ensures containerization and reproducibility. Additionally, it doesn't require having Solr and Java installed and provides more security, because the Solr database and ChromaDB collections are only accessible inside the Docker container. You can either directly pull and run the Docker image or build and run the Docker image locally.

Embedding all theorems into the ChromaDB collection takes about 2 hours, building the FindFacts index with all sessions of the Archive of Formal proofs about 24 hours and informalizing all theorems about 25 hours. This is why I decided to provide prepared tar.gz files of them in the `artifacts/` and `assets/` folder.

In theory, the application only requires a pre-built FindFacts index as a Solr database and the application will start the informalization and embedding process of all necessary theorems. You can confirm/test this by deleting or renaming the `chroma_storages` and the `assets` folder in the running Docker container.

### Pulling and running the Docker image

The advantage of pulling and running the Docker image is that all requirements (inside the Docker image) such as Solr, Python, etc. will automatically be met and all modules, such as ChromaDB collections will be included. Personally, I recommend this method.

> ⚠️ **Warning:** The docker image is unfortunately very large (25.6 GB) because it already contains pre-generated LLM informalizations of all ~303,000 theorems, a FindFacts Solr database, a copy of the Archive of Formal Proofs, pre-installed Python packages and ChromaDB collections with all embeddings.

In order to pull the Docker image from https://gitlab.lrz.de, you have to authenticate Docker first, if you haven't already. If you can't authenticate with GitLab, please refer to [Building the Docker image locally](#building-and-running-the-docker-image-locally):

```bash
docker login gitlab.lrz.de:5005
```

Please enter the same username and password that you also use to log in at https://gitlab.lrz.de.

Next, to pull and run the latest Docker image, simply run:

```bash
docker run -p 5000:5000 --gpus all -it gitlab.lrz.de:5005/kadlez/afp-ai-search
```
Alternatively, you can also find this command in `docker_run.sh`.

This command will redirect port 5000 inside the Docker container onto your computer, i.e. accessing port 5000 on your computer will be redirected to port 5000 inside the Docker container. `--gpus all` will only work if the NVIDIA Container Toolkit has been installed and allows Docker to access your GPU. `-it` (interactive, tty) opens a Shell inside the container after running the image.

When the application finished starting up, you can open the website at http://localhost:5000/.

> ⚠️ **Warning:** If the NVIDIA Container Toolkit has not been installed correctly, a GPU that does not support CUDA is used or a NVIDIA driver with an incompatible CUDA version has been installed, the application will automatically fallback to using the CPU, instead. As a result, search queries will take much longer (~20 seconds on an Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz) to process due to slow LLM text generation.

### Building and running the Docker image locally

Building the Docker image locally can be done by running `docker_build.sh`. This script makes sure, that only files that are not ignored by the `.gitignore` are copied to the image. Additionally, it extracts the tar.gz files from the `assets/` folder into the `assets_extracted/` folder before copying them into the Docker image to save Docker image size.

To run the Docker image, simply run:

```bash
docker run -p 5000:5000 --gpus all -it gitlab.lrz.de:5005/kadlez/afp-ai-search
```
Alternatively, you can also find this command in `docker_run.sh`.

This command will redirect port 5000 inside the Docker container onto your computer, i.e. accessing port 5000 on your computer will be redirected to port 5000 inside the Docker container. `--gpus all` will only work if the NVIDIA Container Toolkit has been installed and allows Docker to access your GPU. `-it` (interactive, tty) opens a Shell inside the container after running the image.

When the application finished starting up, you can open the website at http://localhost:5000/.

### Running the Python application locally

To run the Python application locally, you will have to set up all required components, such as a FindFacts index, etc. manually. To do this, follow this process:

1. Create a FindFacts index using the command `isabelle find_facts_index` as explained in my Bachelor thesis. Alternatively you can extract the `find_facts.tar.gz` within the `assets/` folder.
2. [Install Apache Solr](https://solr.apache.org/guide/solr/latest/deployment-guide/installing-solr.html).
3. Start Solr and specify the path to the FindFacts Solr core:
```bash
solr start --force -p 8983 -s /path/to/findfacts/solr/local
```
> ⚠️ **Warning:** If the path to the FindFacts index is not correct, Solr will automatically create a new empty core. Please make sure that you provide the exact path to the Solr folder (e.g. falsely using `/path/to/findfacts/solr` instead of `/path/to/findfacts/solr/local` will result in Solr not finding the Solr core).
4. If necessary, edit the path to the Solr URL in the `config.json#solr_core_url` variable.
5. Extract `afp-2025-branch-default.tar.gz` and `chroma_storages.tar.gz` and edit both paths in the configuration at `config.json#afp_folder` and `config.json#chroma_db_path`.
6. Start the application using Python: `python -m src.app`

#### Benchmark

To run the Benchmark, use `python -m benchmark.benchmark`. If you want to run a full benchmark that compares different strategies that I also compared in my Bachelor thesis, run `run_full_benchmark.sh`.

## Output

<details>
<summary>If everything works correctly, the output should look like this:</summary>

```bash
Solr will start in SolrCloud mode by default in version 10, and you will have to provide --user-managed if you want to stay on the user-managed (aka. standalone) mode.

Java 17 detected. Enabled workaround for SOLR-16463
NOTE: Please install lsof as this script needs it to determine if Solr is listening on port 8983.

Started Solr server on port 8983 (pid=59). Happy searching!

INFO 08-05 16:42:20 [__init__.py:235] Automatically detected platform cuda.
Loading config...
Loading Solr...
Connect to Solr at http://localhost:8983/solr/local...
Ping Solr for health check...
Loading tokenizer...
tokenizer_config.json: 3.98kB [00:00, 22.7MB/s]
tokenizer.model: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 500k/500k [00:00<00:00, 745kB/s]
tokenizer.json: 1.84MB [00:00, 41.8MB/s]
added_tokens.json: 100%|█████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 306/306 [00:00<00:00, 1.84MB/s]
special_tokens_map.json: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 665/665 [00:00<00:00, 6.74MB/s]
Loading prompts...
Building document index...
.cache/document_index.json does not already exist. Fetching all documents...
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-Analysis.toml for entry HOL-Analysis.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL.toml for entry HOL.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-Algebra.toml for entry HOL-Algebra.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-Library.toml for entry HOL-Library.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-Number_Theory.toml for entry HOL-Number_Theory.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-ex.toml for entry HOL-ex.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-Probability.toml for entry HOL-Probability.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-Computational_Algebra.toml for entry HOL-Computational_Algebra.
No metadata file exists at path afp-2025-branch-default/metadata/entries/HOL-Examples.toml for entry HOL-Examples.
No metadata file exists at path afp-2025-branch-default/metadata/entries/Pentagonal_Number_Theorem.toml for entry Pentagonal_Number_Theorem.
Fetching page 2 of 31 pages...
No metadata file exists at path afp-2025-branch-default/metadata/entries/Dedekind_Sums.toml for entry Dedekind_Sums.
Fetching page 3 of 31 pages...
Fetching page 4 of 31 pages...
Fetching page 5 of 31 pages...
Fetching page 6 of 31 pages...
Fetching page 7 of 31 pages...
Fetching page 8 of 31 pages...
Fetching page 9 of 31 pages...
Fetching page 10 of 31 pages...
Fetching page 11 of 31 pages...
Fetching page 12 of 31 pages...
Fetching page 13 of 31 pages...
Fetching page 14 of 31 pages...
Fetching page 15 of 31 pages...
Fetching page 16 of 31 pages...
Fetching page 17 of 31 pages...
Fetching page 18 of 31 pages...
Fetching page 19 of 31 pages...
Fetching page 20 of 31 pages...
Fetching page 21 of 31 pages...
Fetching page 22 of 31 pages...
Fetching page 23 of 31 pages...
Fetching page 24 of 31 pages...
Fetching page 25 of 31 pages...
Fetching page 26 of 31 pages...
Fetching page 27 of 31 pages...
Fetching page 28 of 31 pages...
Fetching page 29 of 31 pages...
Fetching page 30 of 31 pages...
Fetching page 31 of 31 pages...
Getting document descriptions...
Artifact artifacts/microsoft/Phi-3.5-mini-instruct/document_descriptions.json already exists. Loading...
Finished loading artifacts/microsoft/Phi-3.5-mini-instruct/document_descriptions.json
Finding documents that need to be described by the LLM...
100%|█████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 303229/303229 [00:00<00:00, 544866.56it/s]
Found 0 documents that need to be described by the LLM.
No documents need to be described by the LLM.
Parsing LLM descriptions...
100%|█████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 303229/303229 [00:00<00:00, 997069.24it/s]
Warning: Could not extract theorem description using <BEGIN> and <END> from source provided by LLM for 75 documents, thus loading them as-is.
Clean up tokenizer to free up memory
Loading ChromaDB collection...
Loading ChromaDB embedding function...
modules.json: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 349/349 [00:00<00:00, 2.36MB/s]
config_sentence_transformers.json: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 116/116 [00:00<00:00, 981kB/s]
README.md: 9.52kB [00:00, 16.6MB/s]
sentence_bert_config.json: 100%|████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 53.0/53.0 [00:00<00:00, 660kB/s]
config.json: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 523/523 [00:00<00:00, 7.31MB/s]
model.safetensors: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 265M/265M [00:07<00:00, 35.3MB/s]
tokenizer_config.json: 100%|█████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 333/333 [00:00<00:00, 5.68MB/s]
vocab.txt: 232kB [00:00, 99.4MB/s]
tokenizer.json: 466kB [00:00, 122MB/s]
special_tokens_map.json: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 112/112 [00:00<00:00, 2.00MB/s]
config.json: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 190/190 [00:00<00:00, 3.35MB/s]
Loading ChromaDB collection at path 'chroma_storages/microsoft/Phi-3.5-mini-instruct/chroma_db'...
Preparing documents before adding to ChromaDB collection...
0 documents are still missing in ChromaDB collection.
Loading LLM...
Downloading: 100%|██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 2.18G/2.18G [00:32<00:00, 67.8MiB/s]
Verifying: 100%|█████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 2.18G/2.18G [00:02<00:00, 793MiB/s]
Loading LLM output cache if enabled via config...
Warning: LLM output cache file '.cache/llm_output_cache.json' does not exist, thus a new one will be created.
Preparing Flask app...
Serving Flask API on port 5000... Open: http://localhost:5000/
```
</details>

You can access the website at http://localhost:5000/.

## Screenshot

Below you can find a screenshot of the web UI:

![Screenshot of the web UI](paper/latex/website_screenshot.jpg)

## Pre-Commit hooks

This project uses [ruff](https://pypi.org/project/ruff/) and other pre-commit hooks from the [pre-commit/pre-commit-hooks](https://github.com/pre-commit/pre-commit-hooks) (licensed under the MIT License) repository, which are configured in the `.pre-commit-config.yaml` to follow formatting and linting standards and best practices.

When continuing development, I suggest installing `pre-commits` first:
```bash
pre-commit install
```

## Acknowledgment

I would like to take this opportunity to thank everyone who supported me in creating this thesis. First, I would like to thank Prof. Dr. Jasmin Blanchette for evaluating my thesis and for the insightful advice and constructive criticism I received at the beginning of this thesis and during my first presentation. I would also like to express my sincere gratitude to Balazs Toth, my mentor, who provided me with valuable feedback and support throughout the development of the program and the entire writing process. I would also like to thank Fabian Huch, the developer of FindFacts, for his help and advice. Also, I would like to thank my family and my girlfriend for their motivation and support with proofreading.
