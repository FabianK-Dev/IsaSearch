"""Export a stopped IsaSearch corpus without generation or embedding calls.

Run ``python -m src.export_index -c config.json -o export`` while corpus updates
are stopped. Chroma's public API is used: no dependency on its private SQLite or
HNSW layout. This module deliberately does not import bootstrap or embeddings.
"""

import argparse
import hashlib
import json
import math
import shutil
import struct
import tempfile
import zlib
from pathlib import Path

import tomllib

KINDS = {
    "theorems": ("afp_docs", "document_index.json", "document_descriptions.json"),
    "definitions": (
        "afp_definitions",
        "definition_index.json",
        "definition_descriptions.json",
    ),
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def marked(text):
    if "<BEGIN>" in text:
        text = text.split("<BEGIN>", 1)[1]
    return text.split("<END>", 1)[0].strip()


def file_hash(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def metric_of(collection):
    configuration = getattr(collection, "configuration", {}) or {}
    metric = configuration.get("hnsw", {}).get("space")
    metric = metric or (collection.metadata or {}).get("hnsw:space", "l2")
    if metric not in ("l2", "cosine"):
        raise ValueError(f"Unsupported collection distance metric: {metric}")
    return metric


def export_collection(
    collection, documents, descriptions, source_lookup, directory, kind, recipe
):
    """Public, independently testable streaming export; never calls an embedder."""
    directory = Path(directory)
    directory.mkdir()
    count = collection.count()
    if not count:
        raise ValueError(f"Empty {kind} collection")
    dimension = None
    seen = set()
    metric = metric_of(collection)
    with (
        (directory / "documents.jsonl").open("w", encoding="utf-8") as docs_out,
        (directory / "vectors.f32").open("wb") as vectors_out,
    ):
        for offset in range(0, count, 256):
            batch = collection.get(
                offset=offset,
                limit=256,
                include=["embeddings", "documents", "metadatas"],
            )
            sources = source_lookup(batch["ids"])
            for i, identifier in enumerate(batch["ids"]):
                if identifier in seen:
                    raise ValueError("Collection changed during export: duplicate ID")
                seen.add(identifier)
                if (
                    identifier not in documents
                    or identifier not in descriptions
                    or identifier not in sources
                ):
                    raise ValueError(
                        f"Missing source/cache/description for {identifier}"
                    )
                doc = {**documents[identifier], **sources[identifier]}
                source = doc["src"]
                if documents[identifier]["src"] != source:
                    raise ValueError(f"Stale source cache for {identifier}")
                checksum = zlib.adler32(source.encode("utf-8"))
                metadata = batch["metadatas"][i] or {}
                if metadata.get("source", identifier) != identifier:
                    raise ValueError(f"Vector/source ID mismatch: {identifier}")
                if metadata.get("checksum", checksum) != checksum:
                    raise ValueError(f"Stale embedding for {identifier}")
                description = descriptions[identifier]
                if description.get("zlib.adler32_checksum", checksum) != checksum:
                    raise ValueError(f"Stale description for {identifier}")
                text = batch["documents"][i]
                if not isinstance(text, str):
                    raise TypeError(f"Missing exact embedding input for {identifier}")
                expected = recipe["prompts"]["embed"].format(
                    doc_src=marked(description["llm_description"]).strip()
                    + "\n\n"
                    + source.strip()
                )
                if text != expected:
                    raise ValueError(
                        f"Embedding input disagrees with description/source/prompt: {identifier}"
                    )
                doc.update(
                    id=identifier,
                    kind=kind,
                    checksum=checksum,
                    llm_description=marked(description["llm_description"]),
                    embedding_input=text,
                    description_artifact=description,
                    entry=identifier.split("/thys/", 1)[1].split("/", 1)[0]
                    if "/thys/" in identifier
                    else doc.get("entry", ""),
                )
                for key in ("html", "xml"):
                    doc.pop(key, None)
                vector = [float(x) for x in batch["embeddings"][i]]
                dimension = dimension or len(vector)
                if (
                    not dimension
                    or len(vector) != dimension
                    or not all(map(math.isfinite, vector))
                ):
                    raise ValueError(f"Invalid vector for {identifier}")
                if metric == "cosine" and not any(vector):
                    raise ValueError(f"Zero cosine vector for {identifier}")
                packed = struct.pack(f"<{dimension}f", *vector)
                if not all(map(math.isfinite, struct.unpack(f"<{dimension}f", packed))):
                    raise ValueError(f"Vector overflows float32 for {identifier}")
                vectors_out.write(packed)
                docs_out.write(
                    json.dumps(doc, ensure_ascii=False, allow_nan=False) + "\n"
                )
    if len(seen) != count or collection.count() != count:
        raise ValueError("Collection changed during export")
    return {
        "kind": kind,
        "count": count,
        "dimension": dimension,
        "metric": metric,
        "recipe": recipe,
        "files": {
            name: file_hash(directory / name)
            for name in ("documents.jsonl", "vectors.f32")
        },
    }


def export(config_path, output, kinds=None):
    import chromadb
    import requests

    config_path = Path(config_path).resolve()
    config = read_json(config_path)
    base = config_path.parent
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(base / config["chroma_db_path"] / "chroma_db")
    )
    available = {c.name for c in client.list_collections()}
    prompts = {
        p.stem: p.read_text(encoding="utf-8")
        for p in (base / config["prompts_folder"]).glob("*.txt")
    }
    backend = config.get("embedding_backend", "sentence_transformers")
    recipe = {
        "model": config["openai_embedding_model"]
        if backend == "openai"
        else config["chroma_db_embedder"],
        "backend": backend,
        "max_characters": config.get("openai_embedding_max_characters", 8000)
        if backend == "openai"
        else 0,
        "add_metadata": config.get("add_metadata", False),
        "document_model": config.get(
            f"{config.get('llm_backend', 'ollama')}_document_model", ""
        ),
        "prompts": prompts,
    }
    afp = base / config.get("components", {}).get("afp", {}).get("local_folder", "afp")
    dates = {}
    for path in (afp / "metadata" / "entries").glob("*.toml"):
        with path.open("rb") as stream:
            date = tomllib.load(stream).get("date")
            if date is not None:
                dates[path.stem] = str(date)

    def lookup(ids):
        # Solr's terms parser receives IDs as a parameter, not query syntax.
        if any("\n" in x for x in ids):
            raise ValueError("Newline in document ID")
        response = requests.post(
            config["solr_core_url"].rstrip("/") + "/select",
            data={
                "q": "{!terms f=id separator=$sep v=$ids}",
                "sep": "\n",
                "ids": "\n".join(ids),
                "rows": len(ids),
                "wt": "json",
            },
            timeout=120,
        )
        response.raise_for_status()
        records = {}
        for doc in response.json()["response"]["docs"]:
            entry = (
                doc["id"].split("/thys/", 1)[-1].split("/", 1)[0]
                if "/thys/" in doc["id"]
                else ""
            )
            if not entry:
                # FindFacts squashes Isabelle environment references into path components.
                prefixes = ("AFP/", "AFP_BASE/thys/")
                entry = next(
                    (
                        doc["id"][len(prefix) :].split("/", 1)[0]
                        for prefix in prefixes
                        if doc["id"].startswith(prefix)
                    ),
                    "",
                )
            doc["entry"] = entry
            doc["entry_date"] = dates.get(entry, "")
            url_path = doc.get("url_path", "")
            doc["theory_url"] = (
                config.get(
                    "isabelle_remote_theory_url", "https://isabelle.in.tum.de/library"
                ).rstrip("/")
                + "/"
                + url_path
            )
            if entry:
                doc["entry_url"] = (
                    config.get(
                        "afp_remote_entry_url", "https://isa-afp.org/entries"
                    ).rstrip("/")
                    + "/"
                    + entry
                    + ".html"
                )
                relative = doc.get("file", "").split("/thys/", 1)[-1]
                if relative.startswith("AFP/"):
                    relative = relative.removeprefix("AFP/")
                doc["remote_url"] = (
                    config.get("afp_remote_thys_folder_url", "").rstrip("/")
                    + "/"
                    + relative
                    + "#L"
                    + str(doc.get("start_line", 1))
                )
            records[doc["id"]] = doc
        return records

    temp = Path(tempfile.mkdtemp(prefix=".isasearch-export-", dir=output.parent))
    try:
        corpora = []
        for kind in kinds or KINDS:
            name, cache, artifact = KINDS[kind]
            if name not in available:
                if kinds:
                    raise ValueError(f"Missing collection: {name}")
                continue
            collection = client.get_collection(name, embedding_function=None)
            # Persisted OpenAI model metadata is stronger evidence than the current config.
            ef = (getattr(collection, "configuration", {}) or {}).get(
                "embedding_function"
            ) or {}
            saved = ef.get("config", {})
            if saved.get("model_name", recipe["model"]) != recipe["model"]:
                raise ValueError(
                    f"Configured embedder differs from persisted model in {name}"
                )
            if (
                saved.get("max_characters", recipe["max_characters"])
                != recipe["max_characters"]
            ):
                raise ValueError(
                    f"Configured truncation differs from persisted embedder in {name}"
                )
            corpora.append(
                export_collection(
                    collection,
                    read_json(base / config["cache_folder"] / cache),
                    read_json(base / config["artifacts_folder"] / artifact),
                    lookup,
                    temp / kind,
                    kind,
                    recipe,
                )
            )
        if not corpora:
            raise ValueError("No collections available to export")
        manifest = {
            "format": "isasearch",
            "version": 1,
            "corpora": corpora,
            "provenance": {
                "source": "python",
                "afp": config.get("components", {}).get("afp", {}),
            },
        }
        (temp / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        temp.rename(output)
    except BaseException:
        shutil.rmtree(temp)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", default="config.json")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--kind", choices=KINDS, action="append")
    args = parser.parse_args()
    export(args.config, args.output, args.kind)
    print(f"Exported index to {args.output}")


if __name__ == "__main__":
    main()
