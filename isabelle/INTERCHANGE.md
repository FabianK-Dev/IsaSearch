# IsaSearch interchange format, version 1

The interchange format holds the documents and vectors of an index independently of Lucene.
Builds write it and import it into a new generation; `isasearch_export -F interchange` writes it
from an installed index.

A directory contains `manifest.json` and one subdirectory per corpus (`theorems`,
`definitions`), each with `documents.jsonl` and `vectors.f32`: record n belongs to vector n.

## Manifest

```json
{
  "format": "isasearch",
  "version": 1,
  "corpora": [{
    "kind": "theorems",
    "count": 1,
    "dimension": 2,
    "metric": "cosine",
    "recipe": {
      "model": "actual-model-identity",
      "backend": "openai",
      "max_characters": 8000,
      "add_metadata": false,
      "document_model": "description-model",
      "prompts": {
        "embed": "{doc_src}",
        "retrieve": "{search_query}",
        "search_refine": "Expand {search_query}"
      }
    },
    "files": {
      "documents.jsonl": "sha256-hex-digest",
      "vectors.f32": "sha256-hex-digest"
    },
    "reference_embeddings": [
      {"input": "commutativity of addition", "vector": [0.6, 0.8]}
    ]
  }],
  "provenance": {"source": "scala"}
}
```

- `metric`: `cosine` (1 minus cosine similarity) or `l2` (squared Euclidean distance).
- `count` and `dimension` are positive; absent corpora are omitted.
- `files`: SHA-256 of the exact bytes of each file.
- `recipe` records the prompt texts themselves. `max_characters` counts Unicode code points;
  0 means no truncation. Endpoints and credentials are never recorded.
- `reference_embeddings` (optional): short inputs with their vectors from the index's embedder,
  sent through the `retrieve` prompt as searches send queries. Searches embed them again to
  detect an incompatible embedder; without them, they embed two documents per corpus.
- `truncated_descriptions` and `undescribed_documents` (optional) list document IDs whose
  description was cut off at `max_tokens` or could not be generated; readers ignore them.

## Files

`vectors.f32` holds count × dimension finite little-endian IEEE-754 float32 values, without
header or padding. Zero vectors are invalid for `cosine`.

Each line of `documents.jsonl` is a record with at least `id` (unique within the corpus),
`kind`, `src`, `llm_description`, `embedding_input` (the exact text embedded, before
truncation) and `checksum` (unsigned Adler-32 of the UTF-8 source). `description_artifact`
keeps the original description, prompt and source checksum. The other FindFacts fields are kept
except generated HTML/XML, e.g. `entity_kname`, `chapter`, `session`, `theory`, `file`,
`command`, `start_line`, `consts`, `typs`, `thms`, `url_path`, `entry`, `entry_date`,
`metadata`. Links that do not apply are empty: `theory_url` is set only for distribution
theories, `entry_url` and `remote_url` only for AFP documents.

## Shipped generations

By default `isasearch_export` writes a generation as it is: its `manifest.json` and its Solr
home `solr/`, one core per corpus. The manifest is the generation's, with one more entry:

```json
"generation": {
  "lucene": "9.12.2",
  "files": {"solr/theorems/data/index/_0.cfs": "sha256-hex-digest"}
}
```

`files` lists every file except the manifest by relative path; `lucene` is the version that
wrote the index. `isasearch_import` checks the files, requires a Lucene of the same major
version that is not older, moves the directory into place (copies it from another file system),
opens it and publishes it. Another Lucene version needs the interchange export.
