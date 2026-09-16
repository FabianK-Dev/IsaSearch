"""Replay the paper's noisy inputs without regenerating or mutating them."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

PAPER_INDEX = Path(__file__).parent / "results" / "paper-baselines.json"
NATURAL_QUERY = "Natural language query"
NOISY_QUERY = "Noisy natural language query"


@dataclass(frozen=True)
class PaperNoisyQueries:
    queries: dict
    provenance: dict

    def get(self, target_id, natural_query):
        reference = self.queries.get(target_id)
        if reference is None:
            return None
        if natural_query != reference[NATURAL_QUERY]["query"]:
            raise ValueError(
                f"Natural-language query for '{target_id}' differs from the paper. "
                "Cannot pair it with the paper's saved noisy query."
            )
        return reference[NOISY_QUERY]["query"]


def load_paper_noisy_queries(index_path=PAPER_INDEX):
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
        for kind in (NATURAL_QUERY, NOISY_QUERY):
            if not isinstance(reference.get(kind, {}).get("query"), str):
                raise ValueError(f"Paper query source lacks '{kind}' for '{target}'")
        queries[target] = reference
    return PaperNoisyQueries(
        queries=queries,
        provenance={
            "mode": "replay_paper_noisy_queries",
            "reference_strategy": "UR",
            "reference_result": baseline["result_file"],
            "reference_sha256": digest,
            "available_noisy_queries": len(queries),
            "missing_noisy_query_policy": "skip_query",
        },
    )
