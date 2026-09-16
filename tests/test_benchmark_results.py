"""Offline checks for run preservation and fair comparisons with legacy results."""

import hashlib
import json
import random
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from benchmark.compare import compare, load_result, report
from benchmark.queries import (
    NATURAL_QUERY,
    NOISY_QUERY,
    PAPER_INDEX,
    load_paper_noisy_queries,
)
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


class PaperQueryTest(unittest.TestCase):
    def test_every_paper_strategy_has_the_same_frozen_noisy_inputs(self):
        replay = load_paper_noisy_queries()
        index = json.loads(PAPER_INDEX.read_text())
        self.assertEqual(len(replay.queries), 85)
        for baseline in index["baselines"].values():
            results = load_result(PAPER_INDEX.parent / baseline["result_file"])
            for target, entry in results.items():
                if target == "summary" or entry.get("metadata", {}).get("skipped"):
                    continue
                queries = entry["queries"]
                self.assertEqual(
                    replay.get(target, queries[NATURAL_QUERY]["query"]),
                    queries[NOISY_QUERY]["query"],
                )

    def test_order_and_other_random_draws_cannot_change_replayed_queries(self):
        replay = load_paper_noisy_queries()
        before = random.getstate()
        self.addCleanup(random.setstate, before)
        for target in reversed(replay.queries):
            random.random()
            queries = replay.queries[target]
            self.assertEqual(
                replay.get(target, queries[NATURAL_QUERY]["query"]),
                queries[NOISY_QUERY]["query"],
            )
        self.assertIsNone(replay.get("cramers-rule", "new target"))

    def test_changed_natural_language_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "differs from the paper"):
            load_paper_noisy_queries().get("fundamental-theorem-of-algebra", "changed")

    def test_modified_paper_result_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper-baselines.json"
            index = json.loads(PAPER_INDEX.read_text())
            path.write_text(json.dumps(index))
            Path(folder, index["baselines"]["UR"]["result_file"]).write_text("{}")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                load_paper_noisy_queries(path)

    def test_benchmark_replays_255_paper_queries_and_records_missing_extra_noise(self):
        import pandas as pd

        from src import bootstrap, embeddings

        replay = load_paper_noisy_queries()
        index = json.loads(PAPER_INDEX.read_text())
        paper = load_result(
            PAPER_INDEX.parent / index["baselines"]["UR"]["result_file"]
        )
        rows = pd.read_csv(PAPER_INDEX.parents[1] / "benchmark.csv")
        rows = rows[rows["ID"].isin([*replay.queries, "cramers-rule"])]
        documents = {
            row["ID"]: json.loads(row["Target Identifier"])[0]
            for _, row in rows.iterrows()
        }
        config = {
            "add_metadata": False,
            "add_user_query": True,
            "benchmark_search_refine": True,
            "benchmark_add_top_results": False,
        }
        components = {
            "solr": None,
            "prompts": {},
            "model": None,
            "llm_output_cache": None,
            "corpora": {
                "theorems": {
                    "document_index": documents,
                    "collection": mock.Mock(count=lambda: len(documents), metadata={}),
                }
            },
        }
        with (
            mock.patch.object(bootstrap, "load_config", return_value=config),
            mock.patch.object(
                bootstrap, "boot_components", return_value=components
            ) as boot,
            mock.patch("pandas.read_csv", return_value=rows),
            mock.patch("benchmark.runs.capture_manifest", return_value={"corpus": {}}),
            mock.patch("benchmark.runs.save_run") as save,
            mock.patch.object(
                embeddings,
                "search",
                return_value={"duration": 0, "refined_query": "expanded"},
            ) as search,
            mock.patch.object(
                embeddings, "search_results_to_docs", return_value={"results": []}
            ),
            mock.patch(
                "nltk.download", side_effect=AssertionError("No downloads needed")
            ),
        ):
            runpy.run_module("benchmark.benchmark", run_name="__main__")

        boot.assert_called_once_with(config, serve=True)
        results, manifest = save.call_args.args
        comparison = compare(paper, results)
        self.assertEqual(comparison["matched_count"], 255)
        self.assertEqual(comparison["changed_queries"], [])
        self.assertEqual(comparison["new_count"], 257)
        self.assertEqual(search.call_count, 257)
        self.assertEqual(
            results["cramers-rule"]["metadata"]["skipped_queries"],
            {NOISY_QUERY: "paper_noisy_query_missing"},
        )
        self.assertEqual(manifest["query_inputs"], replay.provenance)
        self.assertNotIn("noise_seed", manifest)
        self.assertIn("paper_noisy_query_missing", report(paper, results))


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
