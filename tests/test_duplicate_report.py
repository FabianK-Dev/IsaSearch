"""Offline checks for shareable duplicate reports rendered from saved evidence."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src import duplicate_report


def sample_report():
    def candidate(tier, name):
        return {
            "id": f"USER_HOME/afp/thys/Other/T.thy|{name}",
            "entry": "Other",
            "kind": "definitions",
            "command": "definition",
            "entity_kname": name,
            "tier": tier,
            "distance": 0.1,
            "syntactic_similarity": 0.1,
            "verdict": None,
            "justification": None,
            "remote_url": "https://example.org/T.thy#L1",
            "entry_url": "https://example.org/Other.html",
            "src": f'definition {name}: "True"',
        }

    item = {
        "id": "USER_HOME/afp/thys/Source/T.thy|1",
        "entity_kname": "source_name",
        "best_tier": "near-exact",
        "remote_url": "https://example.org/source.thy",
        "src": 'definition source_name: "True"',
        "candidates": [
            candidate(tier, name)
            for tier, name in [
                ("near-exact", "exact_match"),
                ("likely", "likely_match"),
                ("possible", "possible_match"),
                (None, "unclassified_match"),
            ]
        ],
    }
    unclassified = {
        **item,
        "entity_kname": "unclassified_source",
        "best_tier": None,
        "candidates": [candidate(None, "unclassified_only")],
    }
    return {
        "generated_at": "2026-09-16",
        "llm_judge": True,
        "all_candidates": True,
        "thresholds": {
            "strong_distance": 0.05,
            "syntactic": 0.9,
            "distance": 0.3,
            "top_k": 10,
        },
        "sections": {
            "definitions": {
                "aggregates": {"documents": 2, "judge_failures": 0},
                "self_retrieval": {
                    "self_retrieved": 2,
                    "documents": 2,
                    "mean_self_distance": 0.0,
                },
                "synthetic_ground_truth": {"documents_with_known_duplicate": 0},
                "entries": [
                    {
                        "entry": "Source_Entry",
                        "date": None,
                        "documents": 2,
                        "items": [item, unclassified],
                    }
                ],
            }
        },
    }


class DuplicateReportTest(unittest.TestCase):
    def setUp(self):
        self.report = sample_report()
        self.item = self.report["sections"]["definitions"]["entries"][0]["items"][0]

    def test_views_filter_candidates_and_documents_without_mutating_evidence(self):
        original = copy.deepcopy(self.report)
        possible = duplicate_report.render_markdown(self.report)
        exact = duplicate_report.render_markdown(self.report, near_exact_only=True)
        for markdown in (possible, exact):
            self.assertNotIn("unclassified\\_source", markdown)
            self.assertNotIn("unclassified\\_match", markdown)
            self.assertNotIn("unclassified\\_only", markdown)
            self.assertNotIn("no tier", markdown)
            self.assertIn("1 of 2 analysed definitions", markdown)
        self.assertIn("(3 candidate pairs)", possible)
        self.assertIn("(1 candidate pairs)", exact)
        self.assertIn("possible\\_match", possible)
        self.assertIn("likely\\_match", possible)
        self.assertNotIn("possible\\_match", exact)
        self.assertNotIn("likely\\_match", exact)
        self.assertIn("exact\\_match", exact)
        self.assertEqual(self.report, original)

    def test_library_matches_use_the_saved_theory_url_and_source_path(self):
        candidate = self.item["candidates"][0]
        candidate.update(
            id="ISABELLE_HOME/src/HOL/Analysis/Test_Theory.thy|1..2",
            entry=None,
            remote_url="#",
            entry_url="#",
            theory_url="https://example.org/Test_Theory.html",
        )
        markdown = duplicate_report.render_markdown(self.report)
        self.assertIn(
            "[exact\\_match](<https://example.org/Test_Theory.html>)", markdown
        )
        self.assertIn("[Isabelle/src/HOL/Analysis/Test\\_Theory\\.thy]", markdown)
        self.assertNotIn("in ?", markdown)
        self.assertNotIn("](<#>)", markdown)

    def test_missing_links_fall_back_to_source_path_without_fabricating_a_url(self):
        candidate = self.item["candidates"][0]
        candidate.update(
            id="custom/path/Example.thy|5", entry=None, remote_url=None, entry_url=None
        )
        markdown = duplicate_report.render_markdown(self.report)
        self.assertIn("in custom/path/Example\\.thy", markdown)
        self.assertNotIn("in ?", markdown)

    def test_names_and_model_text_are_escaped_without_escaping_source_code(self):
        candidate = self.item["candidates"][0]
        candidate["entity_kname"] = "a_[b]*|thm"
        candidate["justification"] = (
            '"quoted" <tag> & x_y\n# heading [fake](url) `code`'
        )
        candidate["remote_url"] = 'https://example.org/a (b)".thy#L1'
        markdown = duplicate_report.render_markdown(self.report, near_exact_only=True)
        self.assertIn("a\\_\\[b\\]\\*\\|thm", markdown)
        self.assertIn("https://example.org/a%20%28b%29%22.thy#L1", markdown)
        self.assertIn('"quoted" &lt;tag&gt; &amp; x\\_y \\# heading', markdown)
        self.assertIn("\\[fake\\]\\(url\\)", markdown)
        self.assertIn('definition source_name: "True"', markdown)

    def test_fences_cannot_be_closed_by_source_contents(self):
        self.item["src"] = 'text "a"\n```\n# still source\n````\nend'
        markdown = duplicate_report.render_markdown(self.report)
        self.assertIn("`````isabelle\n" + self.item["src"] + "\n`````", markdown)

    def test_compact_view_omits_candidate_excerpts_but_exact_view_keeps_them(self):
        excerpt = self.item["candidates"][0]["src"]
        self.assertNotIn(excerpt, duplicate_report.render_markdown(self.report))
        self.assertIn(
            excerpt, duplicate_report.render_markdown(self.report, near_exact_only=True)
        )

    def test_write_and_regenerate_both_views_preserves_json(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = duplicate_report.write_report(self.report, folder)
            self.assertEqual(set(paths), {"json", "possible", "near_exact"})
            json_path = Path(paths["json"])
            before = json_path.read_bytes()
            self.assertEqual(json.loads(before), self.report)
            for key in ("possible", "near_exact"):
                Path(paths[key]).write_text("old report")
            duplicate_report.main([str(json_path)])
            self.assertEqual(json_path.read_bytes(), before)
            self.assertEqual(
                Path(paths["possible"]).read_text(),
                duplicate_report.render_markdown(self.report),
            )
            self.assertEqual(
                Path(paths["near_exact"]).read_text(),
                duplicate_report.render_markdown(self.report, near_exact_only=True),
            )


if __name__ == "__main__":
    unittest.main()
