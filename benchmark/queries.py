"""Replay the paper's benchmark inputs without regenerating or mutating them."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PAPER_INDEX = Path(__file__).parent / "results" / "paper-baselines.json"
TITLE_QUERY = "Title query"
NATURAL_QUERY = "Natural language query"
NOISY_QUERY = "Noisy natural language query"
QUERY_TYPES = (TITLE_QUERY, NATURAL_QUERY, NOISY_QUERY)


@dataclass(frozen=True)
class PaperQueries:
    queries: dict
    provenance: dict

    def for_row(self, row):
        reference = self.queries.get(row["ID"])
        if reference is not None:
            return {
                kind: {
                    "query": reference[kind]["query"],
                    "source": reference[kind].get("source"),
                }
                for kind in QUERY_TYPES
            }
        # Extra targets have no historical noisy input. Keep their ordinary searches without
        # inventing a noisy variant that could be mistaken for part of the paper benchmark.
        return {
            kind: {
                "query": row[kind],
                "source": row.get("Natural language query source"),
            }
            for kind in (TITLE_QUERY, NATURAL_QUERY)
        }


def load_paper_queries(index_path=PAPER_INDEX):
    index_path = Path(index_path)
    index = json.loads(index_path.read_text())
    # All six paper strategies use identical inputs; UR supplies the canonical copy.
    baseline = index["baselines"]["UR"]
    path = index_path.parent / baseline["result_file"]
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != baseline["results_sha256"]:
        raise ValueError(
            f"Paper query source '{path}' does not match its recorded SHA-256"
        )
    results = json.loads(content)
    queries = {}
    for target, entry in results.items():
        if target == "summary" or entry.get("metadata", {}).get("skipped"):
            continue
        reference = entry["queries"]
        for kind in QUERY_TYPES:
            if not isinstance(reference.get(kind, {}).get("query"), str):
                raise TypeError(
                    f"Paper query source lacks text for '{kind}' in '{target}'"
                )
        queries[target] = reference
    return PaperQueries(
        queries=queries,
        provenance={
            "mode": "replay_paper_queries",
            "reference_strategy": "UR",
            "reference_result": baseline["result_file"],
            "reference_sha256": digest,
            "available_targets": len(queries),
            "available_queries": len(queries) * len(QUERY_TYPES),
            "extra_target_input_policy": "csv_title_and_natural_language",
            "missing_noisy_query_policy": "skip_query",
        },
    )
