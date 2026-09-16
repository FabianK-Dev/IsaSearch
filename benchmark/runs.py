"""Capture benchmark provenance and archive existing results without rerunning queries."""

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from src.openai_api import config_without_secrets


def now():
    return datetime.now(timezone.utc).isoformat()


def benchmark_configuration(config):
    """Resolve the strategy and corpus paths once for evaluation and later archiving."""
    effective = dict(config)
    strategy = "M" if config["add_metadata"] else ""
    if config["add_metadata"]:
        for key in ("artifacts_folder", "prompts_folder", "chroma_db_path"):
            effective[key] += "-with-metadata"
    if config["benchmark_search_refine"]:
        strategy += "UR" if config["add_user_query"] else "R"
    return effective, strategy or "baseline"


def file_hash(path):
    path = Path(path)
    if not path.is_file():
        return None
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def git_state(folder):
    folder = Path(folder)
    # An empty AFP directory must not accidentally resolve to the containing IsaSearch repo.
    if not (folder / ".git").exists():
        return None
    try:

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(folder), *args], text=True, stderr=subprocess.DEVNULL
            ).strip()

        return {
            "commit": git("rev-parse", "HEAD"),
            "tracked_changes": bool(
                git("status", "--porcelain", "--untracked-files=no")
            ),
        }
    except (OSError, subprocess.CalledProcessError):
        return None


def capture_manifest(config, strategy, *, after_run=False, note=""):
    # Heavy runtime imports stay out of the comparison tool.
    from src.documents import (
        descriptions_artifact_path,
        document_index_cache_path,
        read_index_fingerprint,
    )
    from src.embeddings import embedding_model_name
    from src.llm import document_model_name, query_model_name

    versions = {}
    for package in ("chromadb", "nltk", "pandas", "sentence-transformers"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    afp = config.get("components", {}).get("afp", {}).get("local_folder")
    return {
        "schema_version": 1,
        "captured_at": now(),
        "provenance": "captured_after_run_unverified"
        if after_run
        else "captured_at_start",
        "note": note,
        "strategy": strategy,
        "config": config_without_secrets(config),
        "models": {
            "document": document_model_name(config),
            "query": query_model_name(config),
            "embedding": embedding_model_name(config),
        },
        "code": git_state("."),
        "source_sha256": {
            str(path): file_hash(path)
            for folder in ("src", "benchmark")
            for path in sorted(Path(folder).glob("*.py"))
        },
        "afp_checkout": git_state(afp) if afp else None,
        "corpus": {
            "cached_index_fingerprint": read_index_fingerprint(
                config, "document_index.json"
            ),
            "document_index_sha256": file_hash(
                document_index_cache_path(config, "document_index.json")
            ),
            "descriptions_sha256": file_hash(
                descriptions_artifact_path(config, "document_descriptions.json")
            ),
        },
        "benchmark_csv_sha256": file_hash("benchmark/benchmark.csv"),
        "prompts": {
            path.name: path.read_text()
            for path in sorted(Path(config["prompts_folder"]).glob("*.txt"))
        },
        "python": platform.python_version(),
        "packages": versions,
    }


def save_run(results, manifest, output_root="benchmark/results", *, source=None):
    """Keep the legacy result schema intact, with provenance in a sibling manifest."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = Path(output_root) / f"{stamp}_{manifest['strategy']}"
    folder.mkdir(parents=True, exist_ok=False)
    result_bytes = (
        Path(source).read_bytes()
        if source
        else (json.dumps(results, indent=4) + "\n").encode()
    )
    (folder / "results.json").write_bytes(result_bytes)
    manifest = {
        **manifest,
        "archived_at": now(),
        "results_sha256": hashlib.sha256(result_bytes).hexdigest(),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "result", type=Path, help="Existing benchmark JSON to preserve unchanged"
    )
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--note", default="")
    parser.add_argument("--output-root", default="benchmark/results")
    args = parser.parse_args()
    config, strategy = benchmark_configuration(json.loads(args.config.read_text()))
    results = json.loads(args.result.read_text())
    if "summary" not in results:
        parser.error("Expected a benchmark result containing a summary")
    manifest = capture_manifest(config, strategy, after_run=True, note=args.note)
    manifest["source_result"] = args.result.name
    folder = save_run(results, manifest, args.output_root, source=args.result)
    print(f"Archived in {folder}")
    print(
        "Settings describe the current environment; they are not verified historical provenance."
    )


if __name__ == "__main__":
    main()
