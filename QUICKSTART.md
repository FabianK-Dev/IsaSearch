# Quickstart: search the AFP on your machine

Search the theorems and definitions of the AFP and the Isabelle distribution locally, with a
released index. Your machine only embeds the queries.

## Requirements

- [Isabelle2026](https://isabelle.in.tum.de), with `isabelle` on your `PATH` (e.g.
  `/Applications/Isabelle2026.app/bin` on macOS, `Isabelle2026/bin` on Linux). On Windows, run
  all commands in Isabelle's Cygwin terminal (`Cygwin-Terminal.bat` in the Isabelle directory).
- llama.cpp's `llama-server` on your `PATH`:
  - macOS: `brew install llama.cpp`;
  - Linux: `sudo apt install llama.cpp` on Ubuntu 25.10 or newer and Debian unstable; on older
    releases, unpack a prebuilt binary from the
    [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases) (e.g.
    `llama-*-bin-ubuntu-x64.zip`) and add its directory to `PATH`;
  - Windows: `winget install llama.cpp`.
- 16 GB of memory and about 16 GB of free disk: 5.7 GB for the index, 4.3 GB for the embedding
  model, and 5 GB for the download while the index is being installed.

Tested on macOS. Linux should work the same way; Windows is untested.

## 1. Register the component

```sh
git clone https://github.com/FabianK-Dev/IsaSearch.git
cd IsaSearch
isabelle components -u "$PWD/isabelle"
```

If you have no `git`, download the repository as a ZIP file from GitHub and unpack it instead.

## 2. Install the index

```sh
isabelle isasearch_import
```

This downloads a released index (5 GB), checks it and installs it. With a registered AFP
(`isabelle components -u /path/to/afp`), it takes the release that covers your AFP's revision,
also when later AFP changesets did not change the index. In a Mercurial clone, it takes the
release of the newest covered ancestor and warns about your local changesets. Without an AFP,
or if no release covers your revision, it lists the releases and asks which one to install. `-R TAG` names a release directly. An interrupted download resumes where it
stopped.

## 3. Search

```sh
isabelle isasearch_search 'a finite union of countable sets is countable'
isabelle isasearch_search -k definitions 'the greatest common divisor'
isabelle isasearch_server
```

`isasearch_server` serves the website at <http://localhost:5001>. The first search starts
`llama-server` with the query embedder and downloads the model (4.3 GB) once; later searches
take under a second.

Results link to the AFP and the Isabelle library online. With a registered AFP, they also
link to its theory files on your machine, and the website opens them in Isabelle/jEdit or
Isabelle/VSCode at the right line.

## Optional

- **Query expansion**: an LLM rewrites the query before the search. Copy
  `isabelle/etc/search.json`, set `"enabled": true` under `llamacpp_query_server`, and point
  the Isabelle option `isasearch_config` at the copy with a line
  `isasearch_config = "/path/to/search.json"` in `$ISABELLE_HOME_USER/etc/preferences`.
  Then `isasearch_search -r` and the website's refinement checkbox expand queries (a 14 GB
  model; about 4 s per query on an M2 Pro).
- **Agents**: [`pide_ai`](pide_ai) offers the search as a tool of PIDE AI.

More in [`isabelle/README.md`](isabelle/README.md).
