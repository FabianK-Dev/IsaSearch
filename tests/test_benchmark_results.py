"""Offline checks for run preservation and fair comparisons with legacy results."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from benchmark.compare import compare, load_result, report
from benchmark.runs import benchmark_configuration, capture_manifest, save_run


def result(query="same query", hit=0, rr=0, skipped=False):
    return {
        "metadata": {"skipped": skipped},
        "queries": {
            "Natural language query": {
                "query": query,
                "metrics": {
                    "top_k_accuracy": hit,
                    "reciprocal_rank": rr,
                    "normalized_discounted_cumulative_gain": rr,
                },
            }
        },
    }


class ComparisonTest(unittest.TestCase):
    def test_means_use_the_same_queries_and_ignore_stored_summaries(self):
        old = {"a": result(), "old-only": result(hit=1, rr=1), "summary": {}}
        new = {"a": result(hit=1, rr=0.5), "new-only": result(), "summary": {}}
        comparison = compare(old, new)
        self.assertEqual(comparison["matched_count"], 1)
        self.assertIn(("All queries", 1, "Hit@10", 0, 1, 1), comparison["rows"])
        self.assertEqual(
            comparison["old_only"], [("old-only", "Natural language query")]
        )

    def test_changed_noise_and_skipped_targets_are_not_paired(self):
        old = {"a": result("old noise"), "b": result()}
        new = {"a": result("new noise", hit=1), "b": result(skipped=True)}
        comparison = compare(old, new)
        self.assertEqual(comparison["matched_count"], 0)
        self.assertEqual(len(comparison["changed_queries"]), 1)
        self.assertEqual(len(comparison["old_only"]), 1)
        self.assertIn("Changed input text (excluded): 1", report(old, new))

    def test_changed_labels_are_excluded_but_label_order_does_not_matter(self):
        old, new = {"a": result()}, {"a": result()}
        old["a"]["metadata"]["target_identifier"] = [{"id": "x"}, {"id": "y"}]
        new["a"]["metadata"]["target_identifier"] = [{"id": "y"}, {"id": "x"}]
        self.assertEqual(compare(old, new)["matched_count"], 1)
        new["a"]["metadata"]["target_identifier"] = [{"id": "z"}]
        self.assertEqual(compare(old, new)["matched_count"], 0)


class RunStorageTest(unittest.TestCase):
    def test_each_run_is_preserved_and_legacy_json_can_be_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "legacy.json"
            contents = '{"a": ' + json.dumps(result()) + ', "summary": {}}\n'
            source.write_text(contents)
            manifest = {"strategy": "UR"}
            first = save_run({}, manifest, folder, source=source)
            second = save_run({"summary": {}}, manifest, folder)
            self.assertNotEqual(first, second)
            self.assertEqual((first / "results.json").read_bytes(), source.read_bytes())
            self.assertEqual(load_result(first), load_result(source))
            saved = json.loads((first / "manifest.json").read_text())
            self.assertEqual(
                saved["results_sha256"], hashlib.sha256(source.read_bytes()).hexdigest()
            )

    def test_strategy_names_follow_actual_query_expansion(self):
        config = {
            "add_metadata": False,
            "benchmark_search_refine": False,
            "add_user_query": True,
        }
        effective, strategy = benchmark_configuration(config)
        self.assertEqual(strategy, "baseline")
        config["benchmark_search_refine"] = True
        self.assertEqual(benchmark_configuration(config)[1], "UR")
        self.assertFalse(effective["benchmark_search_refine"])

    def test_manifest_redacts_credentials_and_labels_recovered_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            config = {
                "llm_backend": "openai",
                "openai_document_model": "document",
                "openai_query_model": "query",
                "embedding_backend": "openai",
                "openai_embedding_model": "embedding",
                "openai_api_key": "secret-value",
                "cache_folder": folder,
                "artifacts_folder": folder,
                "prompts_folder": folder,
            }
            Path(folder, "retrieve.txt").write_text("query: {search_query}")
            manifest = capture_manifest(config, "UR", after_run=True)
            self.assertNotIn("secret-value", json.dumps(manifest))
            self.assertEqual(manifest["models"]["embedding"], "embedding")
            self.assertEqual(manifest["provenance"], "captured_after_run_unverified")
            self.assertEqual(
                manifest["prompts"]["retrieve.txt"], "query: {search_query}"
            )
            self.assertIsNone(manifest["corpus"]["descriptions_sha256"])


if __name__ == "__main__":
    unittest.main()
