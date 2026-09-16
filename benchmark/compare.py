"""Compare two benchmark result files or run directories on identical query texts."""

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean

METRICS = {
    "Hit@10": "top_k_accuracy",
    "MRR": "reciprocal_rank",
    "NDCG": "normalized_discounted_cumulative_gain",
}


def queries(results):
    return {
        (target, kind): query
        for target, entry in results.items()
        if target != "summary" and not entry.get("metadata", {}).get("skipped")
        for kind, query in entry.get("queries", {}).items()
    }


def compare(old, new):
    before, after = queries(old), queries(new)
    common = before.keys() & after.keys()
    mismatched = sorted(
        key for key in common if before[key]["query"] != after[key]["query"]
    )
    changed_labels = []
    for key in common:
        target, _ = key
        labels = [
            result[target].get("metadata", {}).get("target_identifier")
            for result in (old, new)
        ]
        if all(label is not None for label in labels):
            normalized = [
                sorted(json.dumps(item, sort_keys=True) for item in label)
                for label in labels
            ]
            if normalized[0] != normalized[1]:
                changed_labels.append(key)
    matched = sorted(common - set(mismatched) - set(changed_labels))
    rows = []
    for group in ["All queries", *sorted({kind for _, kind in matched})]:
        keys = [key for key in matched if group == "All queries" or key[1] == group]
        if not keys:
            continue
        for label, metric in METRICS.items():
            old_mean = mean(before[key]["metrics"][metric] for key in keys)
            new_mean = mean(after[key]["metrics"][metric] for key in keys)
            rows.append(
                (group, len(keys), label, old_mean, new_mean, new_mean - old_mean)
            )
    changes = []
    for key in matched:
        delta = (
            after[key]["metrics"]["reciprocal_rank"]
            - before[key]["metrics"]["reciprocal_rank"]
        )
        if delta:
            changes.append((key, delta))
    return {
        "old_count": len(before),
        "new_count": len(after),
        "matched_count": len(matched),
        "changed_queries": mismatched,
        "changed_labels": sorted(changed_labels),
        "old_only": sorted(before.keys() - after.keys()),
        "new_only": sorted(after.keys() - before.keys()),
        "rows": rows,
        "changes": sorted(changes, key=lambda item: (item[1], item[0])),
    }


def load_result(path):
    path = Path(path)
    return json.loads((path / "results.json" if path.is_dir() else path).read_text())


def skipped(results):
    return Counter(
        entry["metadata"].get("skipped_reason", "unspecified")
        for key, entry in results.items()
        if key != "summary" and entry.get("metadata", {}).get("skipped")
    )


def report(old, new):
    data = compare(old, new)
    lines = [
        "# Benchmark comparison",
        "",
        (
            f"Evaluated queries: previous **{data['old_count']}**, current **{data['new_count']}**; "
            f"matched by target, query type and exact input text, excluding known label changes: **{data['matched_count']}**."
        ),
        "",
        "The table recomputes both means on those matched queries. Deltas are current minus previous; positive is better.",
        "",
        "| Query type | N | Metric | Previous | Current | Delta |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ]
    for group, count, metric, before, after, delta in data["rows"]:
        lines.append(
            f"| {group} | {count} | {metric} | {before:.4f} | {after:.4f} | {delta:+.4f} |"
        )
    for label, keys in (
        ("Only in previous", data["old_only"]),
        ("Only in current", data["new_only"]),
        ("Changed input text (excluded)", data["changed_queries"]),
        ("Changed relevance labels (excluded)", data["changed_labels"]),
    ):
        lines.extend(["", f"{label}: {len(keys)}."])
        lines.extend(f"- {target} / {kind}" for target, kind in keys)
    for label, results in (("Previous", old), ("Current", new)):
        lines.extend(["", f"{label} skipped targets:"])
        lines.extend(
            f"- {reason}: {count}" for reason, count in sorted(skipped(results).items())
        )
    for label, changes in (
        (
            "Largest RR regressions",
            [item for item in data["changes"] if item[1] < 0][:10],
        ),
        (
            "Largest RR improvements",
            list(reversed([item for item in data["changes"] if item[1] > 0]))[:10],
        ),
    ):
        lines.extend(["", f"{label}:"])
        lines.extend(
            f"- {target} / {kind}: {delta:+.4f}" for (target, kind), delta in changes
        )
    lines.extend(
        [
            "",
            "Legacy results do not record relevance labels, so label equality cannot be verified for those runs. Matching queries does not control for corpus contents, models or prompts. Check the run manifests. Timing is omitted because cached durations and different hardware are not directly comparable.",
        ]
    )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("previous")
    parser.add_argument("current")
    args = parser.parse_args()
    print(f"Previous: `{args.previous}`\n\nCurrent: `{args.current}`\n")
    print(report(load_result(args.previous), load_result(args.current)), end="")


if __name__ == "__main__":
    main()
