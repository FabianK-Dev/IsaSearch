# IsaSearch interchange version 1

Builds write their corpora as an interchange directory and import it into a new
index generation. It contains `manifest.json` and one subdirectory per present
corpus (`theorems`, `definitions`). Each corpus contains `documents.jsonl` and
`vectors.f32`. Both are ordered identically; record n corresponds to vector n.

The manifest is UTF-8 JSON:

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

`metric` is `cosine` (1 minus cosine similarity) or `l2` (squared Euclidean
distance). Vector values are finite little-endian IEEE-754 float32; cosine zero
vectors are invalid. The binary file has exactly count × dimension × 4 bytes.
There is no header or padding. SHA-256 hashes cover the exact bytes of each file.
An absent corpus is omitted; each present corpus has positive count/dimension.
Corpora may list document IDs under
`truncated_descriptions` (descriptions cut off at `max_tokens`) and
`undescribed_documents` (left out because no description could be generated);
readers ignore both.

Each JSONL record requires `id`, `kind`, `src`, `llm_description`,
`embedding_input`, and `checksum` (unsigned Adler32 of UTF-8 source). IDs are
unique within a corpus. `embedding_input` is the exact text that was embedded,
before backend character truncation. Description markers are removed from
`llm_description`; the original artifact, prompt, and source checksum remain in
`description_artifact`. All other source fields are preserved except generated
HTML/XML. Examples include `entity_kname`, `chapter`, `session`, `theory`, `file`,
`command`, `start_line`, `consts`, `typs`, `thms`, `url_path`, `entry`,
`entry_date`, `metadata`, `theory_url`, `entry_url`, and `remote_url`. Links that
do not apply are empty: `theory_url` points into the Isabelle library and is set
only for distribution theories, while AFP documents carry `entry_url` and
`remote_url`.

The recipe records actual prompt text, not a path to a mutable prompt directory.
A zero `max_characters` means no client-side truncation; a positive value counts
Unicode code points. Endpoint settings and credentials are not part of this file.

`reference_embeddings` (optional) are short inputs with their vectors from the
embedder of the index: builds record a few fixed queries through the `retrieve`
prompt, as searches send them. Searches embed them again and compare the vectors
within `embedding_reference_tolerance`, which detects an incompatible embedding
service at little cost. Without them, searches embed two documents of each corpus
instead, whose inputs are long.

The imported Solr generation retains serialized records and the original float32
vectors in its dense-vector field. Solr/Lucene approximate retrieval selects
candidates; distances are recomputed from these vectors. The interchange
is independent of Solr's private disk format. Packaged native indexes
use Isabelle File_Store and target the bundled Solr/Lucene version; rebuild or
reimport when upgrading an incompatible Isabelle release.

## Shipped generations

`isasearch_export` writes a generation as it is by default: its `manifest.json`
and its Solr home `solr/` with one core per corpus. The manifest is that of the
generation (the interchange manifest it was imported from, whose `files` identify
the corpus data across builds) with one more entry:

```json
"generation": {
  "lucene": "9.12.2",
  "files": {"solr/theorems/data/index/_0.cfs": "sha256-hex-digest"}
}
```

`files` lists every file of the directory except the manifest, by relative path,
and `lucene` the version that wrote the index. `isasearch_import` installs such a
directory without indexing: it checks the files, requires a Lucene of the same
major version that is not older, moves the directory into the index directory
(copies it if it is on another file system), opens it, and publishes it. Another
Lucene version needs the interchange export (`-F interchange`).
