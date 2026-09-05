# IsaSearch interchange version 1

An export directory contains `manifest.json` and one subdirectory per present
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
    }
  }],
  "provenance": {"source": "python"}
}
```

`metric` is `cosine` (1 minus cosine similarity) or `l2` (squared Euclidean
distance). Vector values are finite little-endian IEEE-754 float32; cosine zero
vectors are invalid. The binary file has exactly count × dimension × 4 bytes.
There is no header or padding. SHA-256 hashes cover the exact bytes of each file.
An absent corpus is omitted; each present corpus has positive count/dimension.

Each JSONL record requires `id`, `kind`, `src`, `llm_description`,
`embedding_input`, and `checksum` (unsigned Adler32 of UTF-8 source). IDs are
unique within a corpus. `embedding_input` is the exact text Chroma stored before
backend character truncation. Description markers are removed from
`llm_description`; the original artifact, prompt, and source checksum remain in
`description_artifact`. All other source fields are preserved except generated
HTML/XML. Examples include `entity_kname`, `chapter`, `session`, `theory`, `file`,
`command`, `start_line`, `consts`, `typs`, `thms`, `url_path`, `entry`,
`entry_date`, `metadata`, `theory_url`, `entry_url`, and `remote_url`.

The recipe records actual prompt text, not a path to a mutable prompt directory.
A zero `max_characters` means no client-side truncation; a positive value counts
Unicode code points, matching Python slicing. Endpoint settings and credentials
are not part of this file. The current exporter verifies that stored embedding
inputs match the supplied embed prompt, descriptions and source. Older model
settings that Chroma did not persist cannot be recovered from vectors; reference
validation at query startup detects incompatible services.

The imported Solr generation retains serialized records and the original raw
float32 vectors alongside a dense-vector field. Solr/Lucene approximate retrieval
selects candidates; distances are recomputed from raw vectors. The interchange
is independent of Chroma's and Solr's private disk formats. Packaged native indexes
use Isabelle File_Store and target the bundled Solr/Lucene version; rebuild or
reimport when upgrading an incompatible Isabelle release.
