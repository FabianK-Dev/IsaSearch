"""
duplicate_report.py: Turns the analyses of src/duplicates.py into the two reports of a run, i.e. the
JSON report with all raw numbers and the Markdown report that is meant for human inspection.

This is the only place that knows what a report looks like. It reads the plain data of an analysis
and never the corpora, so changing the wording or the layout of a report cannot affect any number
in it.
"""

import json
import os

from datetime import datetime

from src.duplicate_scoring import (
    entry_of_id,
    TIER_LIKELY,
    TIER_NEAR_EXACT,
    TIER_POSSIBLE,
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


# Render one link, falling back to plain text if no URL is available.
def markdown_link(text, url):
    if url is None or url == "#":
        return text

    return f"[{text}]({url})"


# Render the Markdown report that is meant for human inspection.
def render_markdown(report):
    lines = []
    lines.append("# Duplicate analysis of AFP entries")
    lines.append("")
    lines.append(f"Generated at {report['generated_at']}.")
    lines.append("")
    lines.append(
        "This report lists, for each analysed AFP entry, material that already exists elsewhere in "
        "the Archive of Formal Proofs. The entry's own material is excluded from its results. "
        "Ranking is based on the distance in the embedding space; the tiers are a triage aid for "
        "human inspection and not a verdict, because semantic similarity is not logical duplication."
    )
    lines.append("")
    lines.append("Tiers:")
    lines.append("")
    lines.append(
        f"- `{TIER_NEAR_EXACT}`: distance <= "
        f"{report['thresholds']['strong_distance']} or syntactic similarity >= "
        f"{report['thresholds']['syntactic']}"
    )
    lines.append(f"- `{TIER_LIKELY}`: the LLM judged the pair to be a duplicate")
    lines.append(f"- `{TIER_POSSIBLE}`: distance <= {report['thresholds']['distance']}")
    lines.append("")

    if not report["llm_judge"]:
        lines.append(
            "The LLM adjudication was switched off for this run, so the tiers are based on the "
            f"distance and the syntactic similarity only and no candidate reaches `{TIER_LIKELY}`."
        )
        lines.append("")

    if report.get("cross"):
        lines.append(
            "Cross-kind matching is enabled, so every analysed document was matched against the "
            "definitions *and* the theorems of the AFP. The kind of each candidate is given in "
            "parentheses. Note that the synthetic ground truth below only contains definitions, "
            "while candidates of both kinds compete for the reported places, so its recall is not "
            "comparable to a run without cross-kind matching."
        )
        lines.append("")

    if report.get("all_candidates"):
        lines.append(
            f"Every analysed document is listed with its closest {report['thresholds']['top_k']} "
            "candidates, including the ones that reach no tier."
        )
        lines.append("")

    for kind, section in report["sections"].items():
        lines.append(f"## {kind.capitalize()}")
        lines.append("")

        summary = section["aggregates"]
        lines.append(
            f"{summary['documents_with_near_exact_or_likely_duplicate']} of "
            f"{summary['documents']} analysed {kind} have a near-exact or likely duplicate "
            "elsewhere in the AFP."
        )
        lines.append("")

        control = section["self_retrieval"]
        lines.append(
            f"Positive control: {control['self_retrieved']} of {control['documents']} documents "
            f"retrieved themselves at a distance of about 0 (mean self distance "
            f"{control['mean_self_distance']})."
        )
        lines.append("")

        ground_truth = section["synthetic_ground_truth"]
        if ground_truth["documents_with_known_duplicate"] > 0:
            lines.append(
                f"Synthetic ground truth: {ground_truth['documents_recovered']} of "
                f"{ground_truth['documents_with_known_duplicate']} documents with a syntactically "
                f"near-identical counterpart in another entry were recovered within the top "
                f"{report['thresholds']['top_k']} (recall {ground_truth['recall']:.2f})."
            )
            lines.append("")

        lines.append("Top-1 distance histogram:")
        lines.append("")
        for bucket, count in summary["top_1_distance_histogram"].items():
            lines.append(f"- `{bucket}`: {count}")
        lines.append("")

        if len(summary["overlapping_entries"]) > 0:
            lines.append("Most overlapping entries:")
            lines.append("")
            for overlapping_entry, count in summary["overlapping_entries"].items():
                lines.append(f"- `{overlapping_entry}`: {count} reported candidates")
            lines.append("")

        for entry_section in section["entries"]:
            lines.append(
                f"### {entry_section['entry']} ({entry_section['date'] or 'unknown date'})"
            )
            lines.append("")
            lines.append(
                f"{len(entry_section['items'])} of {entry_section['documents']} {kind} of this "
                "entry have at least one reported candidate."
            )
            lines.append("")

            for item in entry_section["items"]:
                title = item["entity_kname"] or item["id"]
                lines.append(
                    f"#### {markdown_link(title, item['remote_url'])} "
                    f"[{item['best_tier'] or 'no tier'}]"
                )
                lines.append("")
                lines.append("```isabelle")
                lines.append(item["src"].strip())
                lines.append("```")
                lines.append("")

                for candidate in item["candidates"]:
                    candidate_title = candidate["entity_kname"] or candidate["id"]
                    lines.append(
                        f"- **{candidate['tier'] or 'no tier'}** "
                        f"({candidate['command'] or candidate['kind']}) "
                        f"{markdown_link(candidate_title, candidate['remote_url'])} "
                        f"in {markdown_link(candidate['entry'] or '?', candidate['entry_url'])} "
                        f"(distance {candidate['distance']:.4f}, "
                        f"syntactic {candidate['syntactic_similarity']:.2f}"
                        + (
                            f", verdict {candidate['verdict']}"
                            if candidate.get("verdict")
                            else ""
                        )
                        + ")"
                    )

                    if candidate.get("justification"):
                        lines.append(f"  - {candidate['justification']}")

                    lines.append("")
                    lines.append("  ```isabelle")
                    for source_line in candidate["src"].strip().splitlines():
                        lines.append("  " + source_line)
                    lines.append("  ```")
                    lines.append("")

    return "\n".join(lines) + "\n"


# Write the JSON and the Markdown report and return both paths.
def write_report(report, report_folder):
    folder = os.path.join(report_folder, "duplicates")

    if not os.path.exists(folder):
        os.makedirs(folder)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = os.path.join(folder, f"experiment_{timestamp}.json")
    markdown_path = os.path.join(folder, f"experiment_{timestamp}.md")

    with open(json_path, "w") as file:
        json.dump(report, file, indent=4)

    with open(markdown_path, "w") as file:
        file.write(render_markdown(report))

    return json_path, markdown_path
