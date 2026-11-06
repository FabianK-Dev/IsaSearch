# Quickstart: search the AFP on your machine

Search the theorems and definitions of the AFP and the Isabelle distribution locally, with the
index and embeddings of a release. Nothing is computed beyond embedding your queries.

You need Isabelle2026, llama.cpp (`llama-server`, e.g. `brew install llama.cpp`), `zstd`,
16 GB of memory and about 11 GB of disk (5.7 GB index, 4.3 GB embedding model).

## 1. Register the component

```sh
git clone https://github.com/FabianK-Dev/IsaSearch.git
cd IsaSearch
isabelle components -u "$PWD/isabelle"
```

## 2. Install the index of a release

Download all assets of the newest
[release](https://github.com/FabianK-Dev/IsaSearch/releases) (the `isasearch-plain-*.tar.zst.*`
parts, the manifest and `SHA256SUMS`) into one directory, then:

```sh
shasum -a 256 -c SHA256SUMS
cat isasearch-plain-*.tar.zst.* | zstd -d | tar -x
isabelle isasearch_import -f isasearch-plain -i plain
```

The parts hold the index ready to search: the import checks its files and moves the
unpacked directory into place, which takes seconds.

## 3. Search

```sh
isabelle isasearch_search 'a finite union of countable sets is countable'
isabelle isasearch_search -k definitions 'the greatest common divisor'
isabelle isasearch_server
```

The server serves the website at <http://localhost:5001>. The first search starts
`llama-server` with the query embedder and downloads it (4.3 GB) once; later searches take
under a second.

Results link to the AFP repository and the Isabelle library online. With a registered AFP
(`isabelle components -u /path/to/afp`), they also link to its theory files on your machine.

## Optional

- **Query expansion**: copy `isabelle/etc/search.json`, set `"enabled": true` under
  `llamacpp_query_server`, and point the Isabelle option `isasearch_config` at the copy (in
  `$ISABELLE_HOME_USER/etc/preferences`). Then `isasearch_search -r` and the website's
  refinement checkbox expand queries with the model of the server (a 14 GB download, about
  4 s per query on an M2 Pro).
- **Agents**: [`pide_ai`](pide_ai) offers the search as a tool of PIDE AI.

More in [`isabelle/README.md`](isabelle/README.md).
