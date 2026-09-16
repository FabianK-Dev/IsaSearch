"""
duplicate_report.py: Stores the analyses of src/duplicates.py as JSON and renders two Markdown
views for human inspection: all flagged candidates and only near-exact candidates.

This is the only place that knows what a report looks like. It reads the plain data of an analysis
and never the corpora, so changing the wording or the layout of a report cannot affect any number
in it.
"""

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from src.duplicate_scoring import (
    TIER_LIKELY,
    TIER_NEAR_EXACT,
    TIER_POSSIBLE,
    TIERS,
    entry_of_id,
)


# Decide which documents and candidates end up in the report. By default only candidates that reach
# a tier are reported, with 'report_all' every analysed document and every candidate is reported.
def is_reported(analysis, report_all):
    if report_all:
        return len(analysis["candidates"]) > 0

    return analysis["best_tier"] is not None


def is_reported_candidate(candidate, report_all):
    return report_all or candidate["tier"] is not None


# Every analysed document that ends up in the report, together with the candidates of it that do.
# The caller that resolves the links of a report and the one that builds it both need exactly this
# selection, so what "reported" means is decided here once instead of in both of them.
def reported_documents(analyses, report_all):
    for analysis in analyses:
        if not is_reported(analysis, report_all):
            continue

        yield (
            analysis,
            [
                candidate
                for candidate in analysis["candidates"]
                if is_reported_candidate(candidate, report_all)
            ],
        )


# Convert the in-memory analyses into the plain data that is written to the JSON report.
def analyses_to_report(
    analyses, corpus_index, urls, report_all=False, source_excerpt_length=600
):
    items = []

    for analysis, reported_candidates in reported_documents(analyses, report_all):
        doc = analysis["doc"]
        candidates = []

        for candidate in reported_candidates:
            candidate_doc = corpus_index[candidate["id"]]
            candidates.append(
                {
                    "id": candidate["id"],
                    "entry": entry_of_id(candidate["id"]),
                    "kind": candidate["kind"],
                    "entity_kname": candidate_doc.get("entity_kname"),
                    "command": candidate_doc.get("command"),
                    "tier": candidate["tier"],
                    "distance": candidate["distance"],
                    "syntactic_similarity": candidate["syntactic_similarity"],
                    "verdict": candidate.get("verdict"),
                    "justification": candidate.get("justification"),
                    "judge_error": candidate.get("judge_error"),
                    "src": candidate_doc["src"][:source_excerpt_length],
                    **urls.get(candidate["id"], {}),
                }
            )

        items.append(
            {
                "id": doc["id"],
                "entry": analysis["exclude_entry"],
                "entity_kname": doc.get("entity_kname"),
                "command": doc.get("command"),
                "best_tier": analysis["best_tier"],
                "self_rank": analysis["self_rank"],
                "self_distance": analysis["self_distance"],
                "src": doc["src"][:source_excerpt_length],
                **urls.get(doc["id"], {}),
                "candidates": candidates,
            }
        )

    return items


# Report text is data, including LLM explanations and Isabelle names. Keep it on one line
# and escape Markdown/HTML syntax; source excerpts are rendered separately in fenced blocks.
def markdown_text(text):
    text = html.escape(" ".join(str(text).split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|~\-])", r"\\\1", text)


def usable_url(url):
    return bool(url and url != "#")


# Angle-bracket link destinations and percent encoding handle spaces, parentheses and quotes.
def markdown_link(text, url):
    label = markdown_text(text)
    if not usable_url(url):
        return label
    return f"[{label}](<{quote(url, safe=':/?#[]@!$&*+,;=%_-~.')}>)"


def document_url(doc):
    return next(
        (
            doc.get(key)
            for key in ("remote_url", "theory_url")
            if usable_url(doc.get(key))
        ),
        None,
    )


def document_location(doc):
    entry = doc.get("entry") or entry_of_id(doc["id"])
    if entry:
        return entry, doc.get("entry_url")

    # Built-in theories have no AFP entry. Their document IDs retain the source path,
    # and the existing URL resolver supplies a link to Isabelle's library browser.
    source_path = doc["id"].rsplit("|", 1)[0]
    if source_path.startswith("ISABELLE_HOME/"):
        source_path = "Isabelle/" + source_path.removeprefix("ISABELLE_HOME/")
    return source_path, document_url(doc)


def fenced_source(source, indent=""):
    # A source excerpt may itself contain backticks. Its fence must be longer than any run.
    source = source.strip()
    width = max([3, *(len(run) + 1 for run in re.findall(r"`+", source))])
    fence = "`" * width
    return [
        indent + fence + "isabelle",
        *(indent + line for line in source.splitlines()),
        indent + fence,
    ]


def filtered_entries(section, tiers):
    entries = []
    for entry in section["entries"]:
        items = []
        for item in entry["items"]:
            candidates = [c for c in item["candidates"] if c["tier"] in tiers]
            if candidates:
                best_tier = next(
                    tier for tier in TIERS if any(c["tier"] == tier for c in candidates)
                )
                items.append({**item, "candidates": candidates, "best_tier": best_tier})
        entries.append({**entry, "items": items})
    return entries


# Both readable views are derived from the stored evidence. In particular, --all-candidates
# preserves extra neighbours in JSON without flooding the shareable Markdown with unclassified hits.
def render_markdown(report, near_exact_only=False):
    tiers = {TIER_NEAR_EXACT} if near_exact_only else set(TIERS)
    title = "Near-exact matches" if near_exact_only else "Possible duplicates"
    lines = [
        f"# Duplicate analysis: {title}",
        "",
        f"Generated at {markdown_text(report['generated_at'])}.",
        "",
    ]
    lines.extend(
        [
            (
                "The selected AFP entries are compared with the indexed AFP and Isabelle library. "
                "Matches within the source entry are excluded. The tiers guide human review; "
                "semantic or syntactic similarity does not establish logical duplication."
            ),
            "",
            "This report contains only **near-exact** candidates."
            if near_exact_only
            else "This report includes **possible**, **likely**, and **near-exact** candidates. "
            "Unclassified neighbours are omitted. Candidate links open the source or library theory; "
            "the separate near-exact report includes candidate source excerpts for closer inspection.",
            "",
            "Source blocks are excerpts and may end mid-statement; follow the links for complete source.",
            "",
            "Tiers:",
            "",
            (
                f"- `{TIER_NEAR_EXACT}`: distance ≤ {report['thresholds']['strong_distance']} "
                f"or syntactic similarity ≥ {report['thresholds']['syntactic']}."
            ),
        ]
    )
    if not near_exact_only:
        lines.extend(
            [
                f"- `{TIER_LIKELY}`: the LLM judged the pair to be a duplicate.",
                f"- `{TIER_POSSIBLE}`: distance ≤ {report['thresholds']['distance']}.",
            ]
        )
    lines.append("")
    if not report["llm_judge"]:
        lines.extend(
            [
                "LLM judging was disabled. Tiers use only distance and syntactic similarity.",
                "",
            ]
        )
    if report.get("cross"):
        lines.extend(
            [
                (
                    "Cross-kind matching is enabled: each document was compared with both definitions "
                    "and theorems. Synthetic-control recall is not comparable with a run without cross-kind matching."
                ),
                "",
            ]
        )

    for kind, section in report["sections"].items():
        entries = filtered_entries(section, tiers)
        items = [item for entry in entries for item in entry["items"]]
        candidates = [c for item in items for c in item["candidates"]]
        summary = section["aggregates"]
        lines.extend(
            [
                f"## {markdown_text(kind.capitalize())}",
                "",
                (
                    f"{len(items)} of {summary['documents']} analysed {markdown_text(kind)} have matches "
                    f"in this report ({len(candidates)} candidate pairs)."
                ),
                "",
                "Candidate tiers: "
                + ", ".join(
                    f"{sum(c['tier'] == tier for c in candidates)} {tier}"
                    for tier in TIERS
                    if tier in tiers
                )
                + ".",
                "",
            ]
        )
        if summary.get("judge_failures", 0):
            lines.extend(
                [
                    (
                        f"Warning: {summary['judge_failures']} candidate pairs remain unjudged in the full run "
                        "after LLM request failures. Their tiers use only distance and syntactic similarity. "
                        "Rerunning retries these pairs."
                    ),
                    "",
                ]
            )
        control = section["self_retrieval"]
        lines.extend(
            [
                (
                    f"Full-run positive control: {control['self_retrieved']} of {control['documents']} "
                    f"documents retrieved themselves at a distance of about 0 "
                    f"(mean self distance {control['mean_self_distance']})."
                ),
                "",
            ]
        )
        ground_truth = section["synthetic_ground_truth"]
        if ground_truth["documents_with_known_duplicate"] > 0:
            lines.extend(
                [
                    (
                        f"Full-run synthetic control: {ground_truth['documents_recovered']} of "
                        f"{ground_truth['documents_with_known_duplicate']} documents with a syntactically "
                        f"near-identical counterpart in another entry were recovered within the top "
                        f"{report['thresholds']['top_k']} (recall {ground_truth['recall']:.2f})."
                    ),
                    "",
                ]
            )
        # Counts belong to this view, not to the unfiltered run stored in aggregates.
        locations = {}
        for candidate in candidates:
            label, url = document_location(candidate)
            locations[label] = (url, locations.get(label, (None, 0))[1] + 1)
        if locations:
            lines.extend(["Most frequent match locations in this report:", ""])
            for label, (url, count) in sorted(
                locations.items(), key=lambda item: -item[1][1]
            )[:20]:
                lines.append(f"- {markdown_link(label, url)}: {count} candidate pairs")
            lines.append("")

        for entry in entries:
            lines.extend(
                [
                    f"### {markdown_text(entry['entry'])} ({markdown_text(entry['date'] or 'unknown date')})",
                    "",
                    (
                        f"{len(entry['items'])} of {entry['documents']} {markdown_text(kind)} "
                        "have at least one candidate in this report."
                    ),
                    "",
                ]
            )
            for item in entry["items"]:
                lines.extend(
                    [
                        (
                            f"#### {markdown_link(item['entity_kname'] or item['id'], document_url(item))} "
                            f"— {item['best_tier']}"
                        ),
                        "",
                        *fenced_source(item["src"]),
                        "",
                    ]
                )
                for candidate in item["candidates"]:
                    label, location_url = document_location(candidate)
                    verdict = (
                        f", verdict {markdown_text(candidate['verdict'])}"
                        if candidate.get("verdict")
                        else ""
                    )
                    lines.extend(
                        [
                            (
                                f"- **{candidate['tier']}** "
                                f"({markdown_text(candidate['command'] or candidate['kind'])}) "
                                f"{markdown_link(candidate['entity_kname'] or candidate['id'], document_url(candidate))} "
                                f"in {markdown_link(label, location_url)} "
                                f"(distance {candidate['distance']:.4f}, "
                                f"syntactic {candidate['syntactic_similarity']:.2f}{verdict})"
                            ),
                        ]
                    )
                    if candidate.get("justification"):
                        lines.extend(
                            ["", "    " + markdown_text(candidate["justification"])]
                        )
                    if candidate.get("judge_error"):
                        lines.extend(
                            [
                                "",
                                "    **Unjudged: LLM request failed.** "
                                + markdown_text(candidate["judge_error"]),
                            ]
                        )
                    if near_exact_only:
                        lines.extend(
                            ["", *fenced_source(candidate["src"], indent="    ")]
                        )
                    lines.append("")
    return "\n".join(lines) + "\n"


def write_markdown_reports(report, json_path):
    base = Path(json_path).with_suffix("")
    paths = {}
    for name, near_exact_only in (("possible", False), ("near_exact", True)):
        path = base.with_name(base.name + "_" + name.replace("_", "-") + ".md")
        path.write_text(
            render_markdown(report, near_exact_only=near_exact_only), encoding="utf-8"
        )
        paths[name] = str(path)
    return paths


# JSON is the source of truth. The two Markdown views can be regenerated without a corpus or LLM.
def write_report(report, report_folder):
    folder = Path(report_folder) / "duplicates"
    folder.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = folder / f"experiment_{timestamp}.json"
    json_path.write_text(json.dumps(report, indent=4), encoding="utf-8")
    return {"json": str(json_path), **write_markdown_reports(report, json_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Regenerate both duplicate reports from saved JSON; no search or LLM calls."
    )
    parser.add_argument("results", type=Path, help="path to an experiment JSON report")
    args = parser.parse_args(argv)
    report = json.loads(args.results.read_text(encoding="utf-8"))
    for path in write_markdown_reports(report, args.results).values():
        print(f"Wrote report to {path}.")


if __name__ == "__main__":
    main()
