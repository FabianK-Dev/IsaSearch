# AFP AI Search

>An AI-assisted semantic theorem finder for the Archive of Formal Proofs using sentence-transformers, ChromaDB and LLMs.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Requirements

- [Python](https://www.python.org/downloads/) 3.11.2 or higher
- [pip](https://pip.pypa.io/en/stable/installation/) 23.0.1 or higher

**If you want to run this application using Docker (recommended):**
- [Docker](https://docs.docker.com/engine/install/)
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

**If you want to run this application using the GPU (highly recommended):**
- a NVIDIA GPU that supports CUDA
- [NVIDIA drivers](https://www.nvidia.com/en-us/drivers/) that are compatible with CUDA version 12.8 (e.g. NVIDIA driver version 570.153.02)

**If you want to run this application locally without Docker:**
- Java Runtime Environment version 17 or higher
- Apache Solr version 9.8.1 or higher

## Setup

### Quickstart (pulling and running the Docker image)

The advantage of pulling and running the Docker image is that all requirements (inside the Docker image) such as Solr, Python, etc. will automatically be met and all modules, such as ChromaDB collections will be included.

> ⚠️ **Warning:** The docker image is very large (33.9 GB) because it already contains pre-generated LLM informalizations of all ~310,000 theorems, a FindFacts Solr database, a copy of the Archive of Formal Proofs, pre-installed Python packages and ChromaDB collections with all embeddings.

In order to pull the Docker image from https://gitlab.lrz.de, you have to authenticate Docker first, if you haven't already. If you can't authenticate with GitLab, please refer to [Building the Docker image locally](#building-the-docker-image-locally):

```bash
docker login gitlab.lrz.de:5005
```

Please enter the same username and password that you also you to log in at https://gitlab.lrz.de.

Next, to pull and run the latest Docker image, simply run:

```bash
docker run -p 5000:5000 --gpus all -it gitlab.lrz.de:5005/kadlez/afp-ai-search
```
Alternatively, you can also find this command in `docker_run.sh`.

This command will redirect port 5000 inside the Docker container onto your computer, i.e. accessing port 5000 on your computer will be redirected to port 5000 inside the Docker container. `--gpus all` will only work if the NVIDIA Container Toolkit has been installed and allows Docker to access your GPU. `-it` (interactive, tty) opens a Shell inside the container after running the image.

When the application finished starting up, you can open the website at http://localhost:5000/.

> ⚠️ **Warning:** If the NVIDIA Container Toolkit has not been installed correctly, a GPU that does not support CUDA is used or a NVIDIA driver with an incompatible CUDA version has been installed, the application will automatically fallback to using the CPU, instead. As a result, search queries will take much longer (~20 seconds on an Intel(R) Core(TM) i7-8700K CPU @ 3.70GHz) to process due to slow LLM text generation.

### Standalone installation (without Docker)

### Building and running the Docker image locally

Building and running the Docker image locally can be easily done by running:

```bash
cp .gitignore .dockerignore
echo "" >> .dockerignore
echo "Dockerfile" >> .dockerignore

docker build -t gitlab.lrz.de:5005/kadlez/afp-ai-search .
docker run -p 5000:5000 --gpus all -it gitlab.lrz.de:5005/kadlez/afp-ai-search
```
Alternatively, you can also find these commands in `docker_build.sh` and `docker_run.sh`.

## Output

If everything works correctly, the output should look like this:

```bash

```

## Badges
On some READMEs, you may see small images that convey metadata, such as whether or not all the tests are passing for the project. You can use Shields to add some to your README. Many services also have instructions for adding a badge.

## Visuals
Depending on what you are making, it can be a good idea to include screenshots or even a video (you'll frequently see GIFs rather than actual videos). Tools like ttygif can help, but check out Asciinema for a more sophisticated method.

## Installation
Within a particular ecosystem, there may be a common way of installing things, such as using Yarn, NuGet, or Homebrew. However, consider the possibility that whoever is reading your README is a novice and would like more guidance. Listing specific steps helps remove ambiguity and gets people to using your project as quickly as possible. If it only runs in a specific context like a particular programming language version or operating system or has dependencies that have to be installed manually, also add a Requirements subsection.

## Usage
Use examples liberally, and show the expected output if you can. It's helpful to have inline the smallest example of usage that you can demonstrate, while providing links to more sophisticated examples if they are too long to reasonably include in the README.

## Support
Tell people where they can go to for help. It can be any combination of an issue tracker, a chat room, an email address, etc.

## Roadmap
If you have ideas for releases in the future, it is a good idea to list them in the README.

## Pre-Commit

pre-commit install

## Contributing
State if you are open to contributions and what your requirements are for accepting them.

For people who want to make changes to your project, it's helpful to have some documentation on how to get started. Perhaps there is a script that they should run or some environment variables that they need to set. Make these steps explicit. These instructions could also be useful to your future self.

You can also document commands to lint the code or run tests. These steps help to ensure high code quality and reduce the likelihood that the changes inadvertently break something. Having instructions for running tests is especially helpful if it requires external setup, such as starting a Selenium server for testing in a browser.

## Authors and acknowledgment
Show your appreciation to those who have contributed to the project.

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
