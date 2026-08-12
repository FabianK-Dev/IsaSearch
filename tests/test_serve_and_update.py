"""
test_serve_and_update.py: Offline tests for the two things a deployed server depends on.

1. Serve mode: the web application and the duplicate detection are meant to run next to each other,
   which is only safe as long as every artifact has exactly one writer. These tests pin down that a
   read-only start-up neither fetches nor writes anything, and that it fails loudly instead of
   quietly building when a corpus is missing.
2. The update path: after the AFP was updated, a cached document index has to be noticed as
   outdated, and the ChromaDB collection has to lose the documents that no longer exist and re-embed
   the ones whose source code changed.

These tests need neither a network, nor Solr, nor a GPU server. Run them with
'python3 -m unittest discover -s tests -t .' inside the root folder of the repository, or alone with
'python3 -m unittest tests.test_serve_and_update -v'.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
import zlib

from requests.exceptions import RequestException

from src import documents, duplicates, embeddings, installation, llm, solr
from tests.stub_openai_server import StubOpenAIServer


# A Solr stand-in that answers exactly the two calls the document index needs: a count
# (count_docs, rows=0) and the paged fetch of all documents (fetch_all_docs).
class FakeSolr:
    def __init__(self, docs):
        self.docs = list(docs)
        self.searches = 0

    def search(self, query, start=0, rows=10):
        self.searches += 1
        page = self.docs[start : start + rows] if rows > 0 else []

        return FakeResults(page, len(self.docs))


class FakeResults:
    def __init__(self, page, total):
        self.page = page
        self.raw_response = {"response": {"numFound": total}}

    def __iter__(self):
        return iter(self.page)


# A ChromaDB collection stand-in that only records which ids were deleted, which is all that
# reconcile_collection does with it.
class FakeCollection:
    def __init__(self):
        self.deleted = []

    def delete(self, ids):
        self.deleted.extend(ids)


def solr_document(doc_id, src):
    return {"id": doc_id, "src": src, "session": "Test", "entity_kname": doc_id}


def indexed_document(doc_id, src):
    return {"id": doc_id, "src": src, "entity_kname": doc_id, "metadata": {}}


class TemporaryFolderTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

        self.config = {
            "cache_folder": os.path.join(self.folder, "cache"),
            "artifacts_folder": os.path.join(self.folder, "artifacts"),
            "solr_query": "command:theorem",
            "isabelle_sessions": ["Test_Session"],
            # No AFP checkout exists here, so every entry falls back to empty metadata.
            "components": {"afp": {"local_folder": os.path.join(self.folder, "afp")}},
            "enable_llm_output_cache": True,
            "add_metadata": False,
        }

        os.makedirs(self.config["cache_folder"], exist_ok=True)


class LlmOutputCacheTest(TemporaryFolderTestCase):
    def test_two_entry_points_do_not_share_a_cache_file(self):
        llm.save_llm_output_cache({"model": {"a": 1}}, self.config)
        llm.save_llm_output_cache(
            {"model": {"b": 2}}, self.config, "llm_output_cache_dedup.json"
        )

        application = llm.get_llm_output_cache(self.config)
        duplicates = llm.get_llm_output_cache(
            self.config, "llm_output_cache_dedup.json"
        )

        # Neither run may have overwritten the entries of the other one.
        self.assertEqual(application, {"model": {"a": 1}})
        self.assertEqual(duplicates, {"model": {"b": 2}})

    def test_a_failed_write_keeps_the_previous_cache(self):
        llm.save_llm_output_cache({"model": {"a": 1}}, self.config)

        # A value json.dump cannot serialize fails halfway through writing the temporary file, which
        # is exactly the situation the atomic write exists for.
        with self.assertRaises(TypeError):
            llm.save_llm_output_cache({"model": {"b": {1, 2}}}, self.config)

        self.assertEqual(llm.get_llm_output_cache(self.config), {"model": {"a": 1}})

    def test_a_failed_write_leaves_no_temporary_file_behind(self):
        with self.assertRaises(TypeError):
            llm.save_llm_output_cache({"model": {"b": {1, 2}}}, self.config)

        leftovers = [
            name
            for name in os.listdir(self.config["cache_folder"])
            if name.endswith(".tmp")
        ]

        self.assertEqual(leftovers, [])


class DocumentIndexCacheTest(TemporaryFolderTestCase):
    def setUp(self):
        super().setUp()
        self.solr = FakeSolr([solr_document("thys/A/T.thy|1", "lemma a: True")])

    def build(self, solr=None, read_only=False):
        return documents.build_document_index(
            self.config, solr if solr is not None else self.solr, read_only=read_only
        )

    def test_the_cache_is_reused_while_the_corpus_is_unchanged(self):
        self.build()
        searches_after_build = self.solr.searches

        self.build()

        # Only the count of the fingerprint check may have been requested, not the documents again.
        self.assertEqual(self.solr.searches, searches_after_build + 1)

    def test_documents_added_to_solr_invalidate_the_cache(self):
        index = self.build()
        self.assertEqual(len(index), 1)

        self.solr.docs.append(solr_document("thys/B/T.thy|1", "lemma b: True"))
        index = self.build()

        # Without the fingerprint the cached index of the previous AFP version would be returned
        # here, and the new entry would stay invisible for as long as the cache file exists.
        self.assertEqual(len(index), 2)

    def test_a_cache_without_a_fingerprint_is_refetched_once(self):
        self.build()
        os.remove(documents.index_fingerprint_path(self.config, "document_index.json"))

        self.solr.docs.append(solr_document("thys/B/T.thy|1", "lemma b: True"))

        self.assertEqual(len(self.build()), 2)

    def test_serve_mode_never_fetches(self):
        self.build()
        searches_after_build = self.solr.searches

        self.solr.docs.append(solr_document("thys/B/T.thy|1", "lemma b: True"))
        index = self.build(read_only=True)

        # The stale cache is served as-is: one count for the warning, no page of documents.
        self.assertEqual(len(index), 1)
        self.assertEqual(self.solr.searches, searches_after_build + 1)

    def test_serve_mode_fails_when_the_corpus_was_never_built(self):
        with self.assertRaises(RuntimeError) as raised:
            self.build(read_only=True)

        self.assertIn("--build-corpus-only", str(raised.exception))


class CollectionReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.collection = FakeCollection()
        self.index = {
            "kept": indexed_document("kept", "lemma kept: True"),
            "changed": indexed_document("changed", "lemma changed: False"),
        }

    def checksum(self, doc_id, src):
        return zlib.adler32(src.encode("utf-8"))

    def test_documents_that_left_the_corpus_are_deleted(self):
        existing = {
            "kept": self.checksum("kept", "lemma kept: True"),
            "removed_by_the_afp": 1234,
        }

        remaining = embeddings.reconcile_collection(
            self.collection, self.index, existing, "afp_docs"
        )

        self.assertEqual(self.collection.deleted, ["removed_by_the_afp"])
        self.assertNotIn("removed_by_the_afp", remaining)

    def test_documents_whose_source_changed_are_deleted_so_they_are_embedded_again(
        self,
    ):
        existing = {
            "kept": self.checksum("kept", "lemma kept: True"),
            # The checksum of the source this document had when it was embedded.
            "changed": self.checksum("changed", "lemma changed: True"),
        }

        remaining = embeddings.reconcile_collection(
            self.collection, self.index, existing, "afp_docs"
        )

        self.assertEqual(self.collection.deleted, ["changed"])
        self.assertNotIn("changed", remaining)
        self.assertIn("kept", remaining)

    def test_documents_without_a_checksum_are_left_alone(self):
        # Collections that were built before checksums were stored must not trigger a full
        # re-embedding run, which would cost hours on the whole AFP.
        existing = {"kept": None, "changed": None}

        remaining = embeddings.reconcile_collection(
            self.collection, self.index, existing, "afp_docs"
        )

        self.assertEqual(self.collection.deleted, [])
        self.assertEqual(set(remaining), {"kept", "changed"})

    def test_re_embedding_all_documents_is_allowed(self):
        # An Isabelle release that reformats sources changes every checksum at once. Nothing is lost
        # by that, because every deleted document is embedded again right afterwards, so the guard
        # against removing a large part of a collection must not stand in the way here.
        existing = {
            "kept": self.checksum("kept", "an older source"),
            "changed": self.checksum("changed", "an older source"),
        }

        remaining = embeddings.reconcile_collection(
            self.collection, self.index, existing, "afp_docs"
        )

        self.assertEqual(sorted(self.collection.deleted), ["changed", "kept"])
        self.assertEqual(remaining, {})

    def test_removing_most_of_a_collection_is_refused(self):
        existing = {f"gone_{i}": 1 for i in range(10)}
        existing["kept"] = self.checksum("kept", "lemma kept: True")

        with self.assertRaises(RuntimeError) as raised:
            embeddings.reconcile_collection(
                self.collection, self.index, existing, "afp_docs"
            )

        self.assertEqual(self.collection.deleted, [])
        self.assertIn("does not belong to this collection", str(raised.exception))


class CollectionUpdateTest(unittest.TestCase):
    """reconcile_collection is exercised through get_chromadb_collection against a real ChromaDB
    collection here, because the checksums have to survive the round trip through ChromaDB's
    metadata for an update to be able to tell an outdated embedding from a current one."""

    def setUp(self):
        self.server = StubOpenAIServer().start()
        self.addCleanup(self.server.stop)

        self.chroma_db_path = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.chroma_db_path, True)

        self.config = {
            "embedding_backend": "openai",
            "openai_embedding_base_url": self.server.base_url,
            "openai_embedding_model": "Qwen3-Embedding-4B",
            "openai_embedding_batch_size": 8,
            "chroma_db_path": self.chroma_db_path,
        }
        self.prompts = {"embed": "{doc_src}"}

    def collection(self, index, **kwargs):
        return embeddings.get_chromadb_collection(
            self.config, self.prompts, index, **kwargs
        )

    def described(self, doc_id, src):
        return {"id": doc_id, "src": src, "llm_description": f"describes {doc_id}"}

    def test_an_updated_corpus_gains_removes_and_re_embeds_documents(self):
        index = {
            "a": self.described("a", "lemma a: True"),
            "b": self.described("b", "lemma b: True"),
        }

        self.assertEqual(self.collection(index).count(), 2)

        # The AFP update removes b, changes a and adds c.
        updated = {
            "a": self.described("a", "lemma a: False"),
            "c": self.described("c", "lemma c: True"),
        }
        collection = self.collection(updated)

        self.assertEqual(sorted(collection.get()["ids"]), ["a", "c"])

        # a has to carry the checksum of its new source, i.e. it was really embedded again instead
        # of keeping the vector of the text it no longer has.
        checksums = {
            item["source"]: item["checksum"]
            for item in collection.get(include=["metadatas"])["metadatas"]
        }
        self.assertEqual(checksums["a"], embeddings.source_checksum(updated["a"]))

    def test_serving_neither_embeds_nor_prunes(self):
        index = {"a": self.described("a", "lemma a: True")}
        self.collection(index)

        # A serving process sees a corpus it does not know all of, which must leave the collection
        # exactly as the build left it.
        collection = self.collection({}, add_missing=False)

        self.assertEqual(collection.get()["ids"], ["a"])

    def test_pruning_can_be_switched_off(self):
        index = {"a": self.described("a", "lemma a: True")}
        self.collection(index)

        collection = self.collection(
            {"b": self.described("b", "lemma b: True")}, prune=False
        )

        self.assertEqual(sorted(collection.get()["ids"]), ["a", "b"])


class DuplicatesEntryPointTest(unittest.TestCase):
    """What src/duplicates.py asks boot_components for decides both how much memory a run needs and
    whether it may write. Both are wired from the command line, so they are pinned down here."""

    def boot_arguments(self, argv):
        recorded = {}

        def fake_boot_components(config, **kwargs):
            recorded.update(kwargs)

            # An unavailable definitions corpus makes main() return right after boot_components,
            # which is all this test needs: what matters is what was asked of boot_components.
            return {
                "definition_index": None,
                "definition_collection": None,
                "document_index": {},
                "collection": None,
            }

        with (
            unittest.mock.patch.object(
                duplicates, "boot_components", fake_boot_components
            ),
            unittest.mock.patch.object(duplicates, "load_config", dict),
        ):
            duplicates.main(argv)

        return recorded

    def test_analysing_definitions_does_not_load_the_theorems(self):
        arguments = self.boot_arguments(["--kinds", "definitions"])

        self.assertFalse(arguments["theorems"])
        self.assertEqual(arguments["definitions"], duplicates.DEFINITIONS_BUILD)

    def test_cross_kind_matching_loads_both_corpora(self):
        arguments = self.boot_arguments(["--kinds", "definitions", "--cross"])

        self.assertTrue(arguments["theorems"])

    def test_building_the_corpus_builds_everything_a_deployment_serves(self):
        # The build step of a deployment has to produce the theorem corpus as well, even though the
        # analysed kind defaults to the definitions.
        arguments = self.boot_arguments(["--build-corpus-only"])

        self.assertTrue(arguments["theorems"])
        self.assertEqual(arguments["definitions"], duplicates.DEFINITIONS_BUILD)
        self.assertFalse(arguments["serve"])

    def test_serving_never_builds(self):
        arguments = self.boot_arguments(["--serve", "--kinds", "definitions"])

        self.assertTrue(arguments["serve"])
        self.assertEqual(arguments["definitions"], duplicates.DEFINITIONS_LOAD)

    def test_serving_and_building_contradict_each_other(self):
        with self.assertRaises(SystemExit):
            duplicates.parse_args(["--serve", "--build-corpus-only"])

    def test_serving_and_indexing_contradict_each_other(self):
        with self.assertRaises(SystemExit):
            duplicates.parse_args(["--serve", "--index-only"])

    # The FindFacts indexer writes the index a running Solr holds open, so indexing has to be
    # runnable on its own, before Solr is started and before anything contacts it.
    def test_indexing_only_never_reaches_solr_or_the_backends(self):
        prepared = []

        with (
            unittest.mock.patch.object(
                duplicates,
                "prepare_corpus_sources",
                lambda config: prepared.append(config),
            ),
            unittest.mock.patch.object(
                duplicates, "boot_components", self.fail_on_boot
            ),
            unittest.mock.patch.object(duplicates, "load_config", dict),
        ):
            self.assertEqual(duplicates.main(["--index-only"]), 0)

        self.assertEqual(len(prepared), 1)

    def fail_on_boot(self, *arguments, **keywords):
        self.fail("--index-only must not boot the components")

    # The exit status of the standalone indexing step is the only signal the deployment runbook
    # has. Reporting success after a failed 'isabelle find_facts_index' would make the next step
    # build a corpus from the previous, stale index.
    def test_a_failed_index_build_is_not_reported_as_success(self):
        def failing(config):
            raise RuntimeError("Building the FindFacts index failed")

        with (
            unittest.mock.patch.object(duplicates, "prepare_corpus_sources", failing),
            unittest.mock.patch.object(duplicates, "load_config", dict),
            self.assertRaises(RuntimeError),
        ):
            duplicates.main(["--index-only"])

    def test_the_duplicate_detection_owns_its_llm_cache(self):
        arguments = self.boot_arguments(["--kinds", "definitions"])

        self.assertEqual(arguments["llm_cache_name"], duplicates.DEDUP_LLM_CACHE)
        self.assertNotEqual(duplicates.DEDUP_LLM_CACHE, llm.DEFAULT_LLM_OUTPUT_CACHE)


class BackupRetentionTest(TemporaryFolderTestCase):
    def backups(self):
        return sorted(
            name
            for name in os.listdir(self.folder)
            if name.startswith("find_facts_backup_")
        )

    def write_backups(self, count):
        for i in range(count):
            path = os.path.join(
                self.folder, f"find_facts_backup_2026-01-{i + 1:02d}_00-00-00.tar.gz"
            )

            with open(path, "w") as file:
                file.write("backup")

    def test_only_the_newest_backups_are_kept(self):
        self.write_backups(5)

        installation.prune_backups(
            pathlib.Path(self.folder), {"find_facts_backup_keep": 2}
        )

        self.assertEqual(
            self.backups(),
            [
                "find_facts_backup_2026-01-04_00-00-00.tar.gz",
                "find_facts_backup_2026-01-05_00-00-00.tar.gz",
            ],
        )

    def test_a_failed_indexer_stops_the_build(self):
        config = {
            "components": {
                "isabelle": {"local_folder": self.folder},
                "afp": {"local_folder": self.folder},
            },
            "isabelle_sessions": ["Test_Session"],
        }

        isabelle_bin = os.path.join(self.folder, "bin", "isabelle")
        os.makedirs(os.path.dirname(isabelle_bin), exist_ok=True)

        with open(isabelle_bin, "w") as file:
            file.write("#!/bin/sh\n")

        def failing(command, **keywords):
            raise subprocess.CalledProcessError(1, command)

        with (
            unittest.mock.patch.object(installation.subprocess, "run", failing),
            unittest.mock.patch.object(
                installation.Path, "home", lambda: pathlib.Path(self.folder)
            ),
            self.assertRaises(RuntimeError) as raised,
        ):
            installation.build_index(config)

        self.assertIn("FindFacts index", str(raised.exception))

    def test_retention_can_be_switched_off(self):
        self.write_backups(3)

        installation.prune_backups(
            pathlib.Path(self.folder), {"find_facts_backup_keep": -1}
        )

        self.assertEqual(len(self.backups()), 3)


# A deployed process has no terminal, so connect_solr must never ask a question there. Before this
# was guarded, a Solr that was down took the whole start-up down with an EOFError raised inside the
# exception handler, which hid the actual cause.
class SolrConnectionTest(unittest.TestCase):
    def setUp(self):
        self.config = {"solr_core_url": "http://solr.example:8983/solr/local"}

    def connect(self, isatty, answer=None):
        unreachable = unittest.mock.Mock()
        unreachable.ping.side_effect = RequestException("connection refused")

        self.asked = unittest.mock.Mock(return_value=answer)

        with unittest.mock.patch.object(solr, "pysolr") as pysolr_module:
            pysolr_module.Solr.return_value = unreachable
            pysolr_module.SolrError = Exception

            with (
                unittest.mock.patch("sys.stdin.isatty", return_value=isatty),
                unittest.mock.patch("builtins.input", self.asked),
            ):
                return solr.connect_solr(self.config)

    def test_without_a_terminal_the_failure_names_the_configured_url(self):
        with self.assertRaises(RuntimeError) as raised:
            self.connect(isatty=False)

        self.assertIn(self.config["solr_core_url"], str(raised.exception))
        self.asked.assert_not_called()

    def test_without_a_terminal_the_original_error_is_kept(self):
        with self.assertRaises(RuntimeError) as raised:
            self.connect(isatty=False)

        self.assertIsInstance(raised.exception.__cause__, RequestException)

    def test_with_a_terminal_the_local_instance_is_still_offered(self):
        with self.assertRaises(SystemExit):
            self.connect(isatty=True, answer="n")

        self.asked.assert_called()


if __name__ == "__main__":
    unittest.main()
