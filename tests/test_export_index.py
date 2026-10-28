"""Tests of the exporter that migrates a Python index to the Isabelle component."""

import json
import tempfile
import unittest
import zlib
from pathlib import Path

import chromadb

from src.export_index import export_collection


def fixture(root, metric="cosine", dimension=3, metadata=False):
    client = chromadb.PersistentClient(path=str(root / "chroma"))
    recipe = {
        "model": "fixture",
        "backend": "openai",
        "max_characters": 8000,
        "add_metadata": metadata,
        "document_model": "fixture",
        "prompts": {
            "embed": "{doc_src}",
            "retrieve": "{search_query}",
            "search_refine": "Expand {search_query}",
            "duplicate_judge": "Compare {item_a} and {item_b}",
        },
    }
    export = root / "export"
    export.mkdir(parents=True)
    corpora = []
    embedding_map = {}
    for kind in ("theorems", "definitions"):
        collection = client.create_collection(
            kind, metadata={"hnsw:space": metric}, embedding_function=None
        )
        docs = {}
        descriptions = {}
        vectors = []
        texts = []
        for i, entry in enumerate(("A", "B", "C")):
            identifier = f"AFP/thys/{entry}/T.thy|{kind}{i}"
            command = "lemma" if kind == "theorems" else "definition"
            source = f'{command} x{i}: "a + b = b + a"'
            description = f"Commutativity ∀α 😀 {kind} {i}"
            text = description + "\n\n" + source
            vector = [0.0] * dimension
            vector[0], vector[1] = ((1, 0), (0.99, 0.01), (0, 1))[i]
            checksum = zlib.adler32(source.encode())
            docs[identifier] = {
                "id": identifier,
                "src": source,
                "entity_kname": f"T.x{i}|thm",
                "entry": entry,
                "entry_date": "2026-01-01",
                "command": command,
                "session": entry,
                "start_line": i + 1,
                "consts": ["T.shared"],
                "typs": [],
            }
            descriptions[identifier] = {
                "llm_description": f"<BEGIN>{description}<END>",
                "zlib.adler32_checksum": checksum,
            }
            vectors.append(vector)
            texts.append(text)
            embedding_map[text] = vector
        collection.add(
            ids=list(docs),
            documents=texts,
            embeddings=vectors,
            metadatas=[
                {"source": key, "checksum": zlib.adler32(doc["src"].encode())}
                for key, doc in docs.items()
            ],
        )
        spec = export_collection(
            collection,
            docs,
            descriptions,
            lambda ids, records=docs: {key: records[key] for key in ids},
            export / kind,
            kind,
            recipe,
        )
        corpora.append(spec)
    (export / "manifest.json").write_text(
        json.dumps({"format": "isasearch", "version": 1, "corpora": corpora})
    )
    return export, embedding_map


class ExporterTests(unittest.TestCase):
    def test_export_rejects_stale_artifacts_and_changed_inputs(self):
        with tempfile.TemporaryDirectory(prefix="isasearch-export-") as temporary:
            root = Path(temporary)
            exported, _ = fixture(root)
            records = [
                json.loads(line)
                for line in (exported / "theorems/documents.jsonl")
                .read_text()
                .splitlines()
            ]
            docs = {r["id"]: r for r in records}
            descriptions = {r["id"]: dict(r["description_artifact"]) for r in records}
            spec = json.loads((exported / "manifest.json").read_text())["corpora"][0]
            collection = chromadb.PersistentClient(
                path=str(root / "chroma")
            ).get_collection("theorems", embedding_function=None)
            identifier = records[0]["id"]
            descriptions[identifier]["zlib.adler32_checksum"] = -1
            with self.assertRaisesRegex(ValueError, "Stale description"):
                export_collection(
                    collection,
                    docs,
                    descriptions,
                    lambda ids: docs,
                    root / "stale",
                    "theorems",
                    spec["recipe"],
                )
            descriptions[identifier] = records[0]["description_artifact"]
            collection.update(
                ids=[identifier],
                documents=["incorrect stored input"],
                embeddings=collection.get(ids=[identifier], include=["embeddings"])[
                    "embeddings"
                ],
            )
            with self.assertRaisesRegex(ValueError, "Embedding input disagrees"):
                export_collection(
                    collection,
                    docs,
                    descriptions,
                    lambda ids: docs,
                    root / "changed",
                    "theorems",
                    spec["recipe"],
                )


if __name__ == "__main__":
    unittest.main()
