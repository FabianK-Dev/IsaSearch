"""Cross-language tests. Requires Isabelle2025-2 on PATH and Python requirements.

Run: python -m unittest tests.test_scala_component -v
An isolated Isabelle user directory is created; no user components are registered.
Inference is provided by a local deterministic HTTP stub, never a real model.
"""

import csv
import difflib
import hashlib
import http.server
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zlib
from pathlib import Path

import chromadb

from benchmark import metrics
from src import duplicate_scoring
from src.export_index import export_collection

ROOT = Path(__file__).resolve().parents[1]


def fixture(root, metric="cosine", dimension=3, metadata=False):
    client = chromadb.PersistentClient(path=str(root / "chroma"))
    recipe = {
        "model": "fixture",
        "backend": "openai",
        "max_characters": 8000,
        "add_metadata": metadata,
        "document_model": "fixture",
        "prompts": {
            "embed": "{doc_src}",
            "retrieve": "{search_query}",
            "search_refine": "Expand {search_query}",
            "duplicate_judge": "Compare {item_a} and {item_b}",
        },
    }
    export = root / "export"
    export.mkdir(parents=True)
    corpora = []
    embedding_map = {}
    for kind in ("theorems", "definitions"):
        collection = client.create_collection(
            kind, metadata={"hnsw:space": metric}, embedding_function=None
        )
        docs = {}
        descriptions = {}
        vectors = []
        texts = []
        for i, entry in enumerate(("A", "B", "C")):
            identifier = f"AFP/thys/{entry}/T.thy|{kind}{i}"
            command = "lemma" if kind == "theorems" else "definition"
            source = f'{command} x{i}: "a + b = b + a"'
            description = f"Commutativity ∀α 😀 {kind} {i}"
            text = description + "\n\n" + source
            vector = [0.0] * dimension
            vector[0], vector[1] = ((1, 0), (0.99, 0.01), (0, 1))[i]
            checksum = zlib.adler32(source.encode())
            docs[identifier] = {
                "id": identifier,
                "src": source,
                "entity_kname": f"T.x{i}|thm",
                "entry": entry,
                "entry_date": "2026-01-01",
                "command": command,
                "session": entry,
                "start_line": i + 1,
                "consts": ["T.shared"],
                "typs": [],
            }
            descriptions[identifier] = {
                "llm_description": f"<BEGIN>{description}<END>",
                "zlib.adler32_checksum": checksum,
            }
            vectors.append(vector)
            texts.append(text)
            embedding_map[text] = vector
        collection.add(
            ids=list(docs),
            documents=texts,
            embeddings=vectors,
            metadatas=[
                {"source": key, "checksum": zlib.adler32(doc["src"].encode())}
                for key, doc in docs.items()
            ],
        )
        spec = export_collection(
            collection,
            docs,
            descriptions,
            lambda ids, records=docs: {key: records[key] for key in ids},
            export / kind,
            kind,
            recipe,
        )
        corpora.append(spec)
    (export / "manifest.json").write_text(
        json.dumps({"format": "isasearch", "version": 1, "corpora": corpora})
    )
    return export, embedding_map


def goldens(path):
    pairs = [
        ("abcd", "bcde"),
        ("", ""),
        ("diet", "tide"),
        ("α😀abc", "α😁abc"),
        ("a" * 210 + "xyz", "b" + "a" * 210 + "xyz"),
        ("x" * 500 + "a", "x" * 500 + "b"),
    ]
    stopwords = set(
        (ROOT / "isabelle/benchmark/stopwords_english.txt").read_text().splitlines()
    )
    rng = random.Random(129869)
    noise = []
    for text in [
        "The sum of two numbers is [...] equal to their total.",
        "Every polynomial, over the complex numbers, has a root.",
        "α and 😀 the numbers",
    ]:
        words = re.sub(r"[\[\].,:]", " ", text.replace("[...]", " ")).lower().split()
        words = [w for w in words if w not in stopwords]
        i = 0
        while i < len(words) - 1:
            if rng.random() < 0.1:
                words[i], words[i + 1] = words[i + 1], words[i]
                i += 2
            else:
                i += 1
        result = "".join(c for c in " ".join(words) if rng.random() < 0.9)
        noise.append({"input": text, "output": result})
    cases = [
        ([], [{"id": "a"}]),
        ([{"id": "a"}], [{"id": "a"}]),
        ([{"id": "b"}, {"id": "a"}, {"id": "c"}], [{"id": "a"}, {"id": "c"}]),
        ([{"id": "b"}] * 10 + [{"id": "a"}], [{"id": "a"}]),
        ([{"id": "a"}], []),
        ([{"id": "a"}], [{"id": "a", "missing": "x"}]),
    ]
    ms = []
    for results, targets in cases:
        ms.append(
            {
                "results": results,
                "targets": targets,
                "expected": {
                    "top_k_accuracy": metrics.top_k_accuracy(results, targets),
                    "normalized_discounted_cumulative_gain": metrics.normalized_discounted_cumulative_gain(
                        results, targets
                    ),
                    "reciprocal_rank": metrics.reciprocal_rank(results, targets),
                    "rank": metrics.rank(results, targets),
                },
            }
        )
    path.write_text(
        json.dumps(
            {
                "similarity": [
                    {
                        "a": a,
                        "b": b,
                        "ratio": difflib.SequenceMatcher(None, a, b).ratio(),
                    }
                    for a, b in pairs
                ],
                "noise": noise,
                "metrics": ms,
                "classifications": [
                    {
                        "candidate": c,
                        "tier": duplicate_scoring.classify(
                            c,
                            {
                                "dedup_strong_distance_threshold": 0.05,
                                "dedup_distance_threshold": 0.3,
                                "dedup_syntactic_threshold": 0.9,
                            },
                        )
                        or "",
                    }
                    for c in [
                        {
                            "distance": d,
                            "syntactic_similarity": syntax,
                            "verdict": verdict,
                        }
                        for d in (0.01, 0.05, 0.2, 0.3, 0.8)
                        for syntax in (0, 0.9, 1)
                        for verdict in ("DUPLICATE", "VARIANT", "UNKNOWN")
                    ]
                ],
                "verdicts": [
                    {"input": value, "expected": duplicate_scoring.parse_verdict(value)}
                    for value in (
                        "<BEGIN>VERDICT: duplicate\nSame.<END>",
                        "VERDICT: variant X",
                        "VERDICT: UNKNOWN unrecognized",
                        "No verdict",
                        "VERDICT: alien",
                    )
                ],
                "normalized": [
                    {
                        "input": value,
                        "expected": duplicate_scoring.normalized_statement(value),
                    }
                    for value in (
                        'lemma name [simp]: "x + y = y + x" proof done',
                        'definition name :: "nat ⇒ nat" where "name = id"',
                        'lemma soundness_proof_of: "α = α"',
                        'lemma x: "proof"',
                    )
                ],
            }
        )
    )


class Stub(http.server.ThreadingHTTPServer):
    def __init__(self, vectors):
        self.vectors = vectors
        self.calls = []
        self.mode = "ok"
        self.llm_up = True
        self.transient = 0
        self.completion_mode = "ok"
        self.completion_text = "<BEGIN>VERDICT: DUPLICATE\nSame statement.<END>"
        self.fail_input_contains = ""
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.calls.append((self.path, body, self.headers.get("Authorization")))
                if self.headers.get("Authorization") != "Bearer test-key":
                    self.send_error(401)
                    return
                if self.path.endswith("embeddings") or self.path == "/api/embed":
                    if owner.fail_input_contains and any(
                        owner.fail_input_contains in text for text in body["input"]
                    ):
                        self.send_error(503)
                        return
                    if owner.transient:
                        owner.transient -= 1
                        self.send_error(503)
                        return
                    if owner.mode == "timeout":
                        time.sleep(2.2)
                    vectors = [
                        owner.vectors.get(t, [1.0, 0.0, 0.0]) for t in body["input"]
                    ]
                    if owner.mode == "dimension":
                        vectors = [[1.0]] * len(vectors)
                    if owner.mode == "mismatch":
                        vectors = [[0.0, 0.0, 1.0]] * len(vectors)
                    payload = (
                        {"embeddings": vectors}
                        if self.path == "/api/embed"
                        else {
                            "data": list(
                                reversed(
                                    [
                                        {"index": i, "embedding": v}
                                        for i, v in enumerate(vectors)
                                    ]
                                )
                            )
                        }
                    )
                    if owner.mode == "indices" and "data" in payload:
                        payload["data"] = [
                            {"index": 0, "embedding": v} for v in vectors
                        ]
                else:
                    if not owner.llm_up:
                        self.send_error(503)
                        return
                    text = owner.completion_text
                    if owner.completion_mode == "empty":
                        text = "<BEGIN> <END>"
                    payload = (
                        {
                            "choices": [
                                {"message": {"content": text}, "finish_reason": "stop"}
                            ]
                        }
                        if self.path.endswith("chat/completions")
                        else {"response": text, "content": text, "done_reason": "stop"}
                    )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                try:
                    self.wfile.write(json.dumps(payload).encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass

        super().__init__(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_port}"

    def close(self):
        self.shutdown()
        self.server_close()
        self.thread.join()


class ExporterTests(unittest.TestCase):
    def test_export_rejects_stale_artifacts_and_changed_inputs(self):
        with tempfile.TemporaryDirectory(prefix="isasearch-export-") as temporary:
            root = Path(temporary)
            exported, _ = fixture(root)
            records = [
                json.loads(line)
                for line in (exported / "theorems/documents.jsonl")
                .read_text()
                .splitlines()
            ]
            docs = {r["id"]: r for r in records}
            descriptions = {r["id"]: dict(r["description_artifact"]) for r in records}
            spec = json.loads((exported / "manifest.json").read_text())["corpora"][0]
            collection = chromadb.PersistentClient(
                path=str(root / "chroma")
            ).get_collection("theorems", embedding_function=None)
            identifier = records[0]["id"]
            descriptions[identifier]["zlib.adler32_checksum"] = -1
            with self.assertRaisesRegex(ValueError, "Stale description"):
                export_collection(
                    collection,
                    docs,
                    descriptions,
                    lambda ids: docs,
                    root / "stale",
                    "theorems",
                    spec["recipe"],
                )
            descriptions[identifier] = records[0]["description_artifact"]
            collection.update(
                ids=[identifier],
                documents=["incorrect stored input"],
                embeddings=collection.get(ids=[identifier], include=["embeddings"])[
                    "embeddings"
                ],
            )
            with self.assertRaisesRegex(ValueError, "Embedding input disagrees"):
                export_collection(
                    collection,
                    docs,
                    descriptions,
                    lambda ids: docs,
                    root / "changed",
                    "theorems",
                    spec["recipe"],
                )


@unittest.skipUnless(shutil.which("isabelle"), "Isabelle2025-2 required")
class ScalaComponentTests(unittest.TestCase):
    def test_cross_language_and_api(self):
        with tempfile.TemporaryDirectory(prefix="isasearch-test-") as temp:
            root = Path(temp)
            env = os.environ.copy()
            env["USER_HOME"] = str(root / "home")
            env["ISASEARCH_TEST_KEY"] = "test-key"
            etc = root / "home/.isabelle/Isabelle2025-2/etc"
            etc.mkdir(parents=True)
            (etc / "components").write_text(str(ROOT / "isabelle") + "\n")
            (etc / "settings").write_text(
                'ISABELLE_TOOL_JAVA_OPTIONS="-Djava.awt.headless=true -Xms256m -Xmx4g -Xss16m"\n'
            )

            def run(tool, *args, ok=True):
                process = subprocess.run(
                    ["isabelle", "isasearch_" + tool, *map(str, args)],
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if ok:
                    self.assertEqual(
                        process.returncode, 0, process.stdout + process.stderr
                    )
                else:
                    self.assertNotEqual(process.returncode, 0)
                return process

            plain, vectors = fixture(root / "plain")
            meta, _ = fixture(root / "metadata", metadata=True)
            l2, _ = fixture(root / "l2", metric="l2")
            large, _ = fixture(root / "large", dimension=2048)
            golden = root / "golden.json"
            goldens(golden)
            run("test", golden, plain, l2, large)
            run("import", "-f", plain, "-i", "plain")
            run("import", "-f", meta, "-i", "metadata")
            stub = Stub(vectors)
            self.addCleanup(stub.close)
            config = {
                "embedding_backend": "openai",
                "openai_embedding_model": "fixture",
                "openai_embedding_base_url": stub.url + "/v1",
                "openai_base_url": stub.url + "/v1",
                "openai_api_key_env": "ISASEARCH_TEST_KEY",
                "llm_backend": "none",
                "llm_request_timeout": 2,
                "llm_attempts": 1,
                "enable_llm_output_cache": False,
            }
            config_path = root / "config.json"

            def configure(**changes):
                config.update(changes)
                config_path.write_text(json.dumps(config))

            configure()
            result = run("search", "-c", config_path, "-i", "plain", "commutativity")
            self.assertIn('"results"', result.stdout)
            self.assertFalse(any("chat" in c[0] for c in stub.calls))
            run(
                "search",
                "-c",
                config_path,
                "-i",
                "plain",
                "-r",
                "commutativity",
                ok=False,
            )
            api_log = (root / "api.log").open("w+")
            api = subprocess.Popen(
                [
                    "isabelle",
                    "isasearch_server",
                    "-c",
                    str(config_path),
                    "-i",
                    "plain",
                    "-p",
                    "0",
                ],
                env=env,
                stdout=api_log,
                stderr=api_log,
                start_new_session=True,
            )
            try:
                url = None
                for _ in range(150):
                    api_log.flush()
                    match = re.search(
                        r"IsaSearch API: (http://\S+)", (root / "api.log").read_text()
                    )
                    if match:
                        url = match.group(1)
                        break
                    if api.poll() is not None:
                        self.fail((root / "api.log").read_text())
                    time.sleep(0.1)
                self.assertIsNotNone(url)
                with urllib.request.urlopen(
                    url + "/capabilities", timeout=30
                ) as response:
                    capabilities = json.load(response)
                self.assertTrue(capabilities["embedding_available"])
                self.assertFalse(capabilities["query_expansion"])
                for query, status in [
                    ("?query=test&refine_query=true", 503),
                    ("?query=", 400),
                    ("?query=test&kind=bad", 400),
                ]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(url + "/search" + query, timeout=30)
                    self.assertEqual(caught.exception.code, status)
                    caught.exception.close()
                with urllib.request.urlopen(
                    url + "/search?query=test", timeout=30
                ) as response:
                    self.assertEqual(len(json.load(response)["results"]), 3)
                stub.mode = "dimension"
                with self.assertRaises(urllib.error.HTTPError) as failed:
                    urllib.request.urlopen(
                        url + "/search?query=unavailable", timeout=30
                    )
                self.assertEqual(failed.exception.code, 503)
                failed.exception.close()
                with urllib.request.urlopen(
                    url + "/capabilities", timeout=30
                ) as response:
                    self.assertFalse(json.load(response)["embedding_available"])
                stub.mode = "ok"
            finally:
                import signal

                os.killpg(api.pid, signal.SIGTERM)
                api.wait(timeout=15)
                api_log.close()
            packaged = Path(
                run(
                    "index_build", "-i", "plain", "-D", root / "packages"
                ).stdout.strip()
            )
            archive = packaged / "plain.db"
            archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            archive.chmod(0o400)
            (etc / "components").write_text(
                str(ROOT / "isabelle") + "\n" + str(packaged) + "\n"
            )
            shutil.rmtree(
                root / "home/.isabelle/Isabelle2025-2/isasearch/indexes/plain"
            )
            run("search", "-c", config_path, "-i", "plain", "relocated")
            self.assertEqual(
                hashlib.sha256(archive.read_bytes()).hexdigest(), archive_hash
            )
            for backend in ("openai", "ollama", "llamacpp"):
                configure(
                    llm_backend=backend,
                    embedding_backend="ollama" if backend == "ollama" else "openai",
                    **{
                        backend + "_query_model": "fixture",
                        "ollama_base_url": stub.url,
                        "llamacpp_base_url": stub.url,
                    },
                )
                run("search", "-c", config_path, "-i", "plain", "-r", "commutativity")
            stub.transient = 1
            run("search", "-c", config_path, "-i", "plain", "retry")
            self.assertEqual(stub.transient, 0)
            stub.mode = "indices"
            run("search", "-c", config_path, "-i", "plain", "test", ok=False)
            configure(embedding_attempts=1)
            stub.mode = "timeout"
            run("search", "-c", config_path, "-i", "plain", "test", ok=False)
            stub.mode = "dimension"
            run("search", "-c", config_path, "-i", "plain", "test", ok=False)
            stub.mode = "mismatch"
            run("search", "-c", config_path, "-i", "plain", "test", ok=False)
            stub.mode = "ok"
            configure(
                llm_backend="openai",
                embedding_backend="openai",
                openai_query_model="fixture",
            )
            stub.completion_mode = "empty"
            run("search", "-c", config_path, "-i", "plain", "-r", "test", ok=False)
            stub.completion_mode = "ok"
            stub.llm_up = False
            run("search", "-c", config_path, "-i", "plain", "-r", "test", ok=False)
            stub.llm_up = True
            configure(enable_llm_output_cache=True)
            first = json.loads(
                run(
                    "search", "-c", config_path, "-i", "plain", "-r", "cached query"
                ).stdout
            )
            second = json.loads(
                run(
                    "search", "-c", config_path, "-i", "plain", "-r", "cached query"
                ).stdout
            )
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertGreaterEqual(second["duration"], second["elapsed_duration"])
            # llama.cpp omits the model from its request body, but its cache must
            # still follow the configured model when a server changes models.
            configure(llm_backend="llamacpp", llamacpp_query_model="model-a")
            original_completion = stub.completion_text
            for model, answer, cached in (
                ("model-a", "Model A answer", False),
                ("model-b", "Model B answer", False),
                ("model-b", "Model B answer", True),
                ("model-a", "Model A answer", True),
            ):
                configure(llamacpp_query_model=model)
                stub.completion_text = f"<BEGIN>{answer}<END>"
                response = json.loads(
                    run(
                        "search", "-c", config_path, "-i", "plain", "-r", "model cache"
                    ).stdout
                )
                self.assertEqual(response["refined_query"], answer)
                self.assertEqual(response["cache_hit"], cached)
            stub.completion_text = original_completion
            configure(llm_backend="openai", enable_llm_output_cache=False)
            dataset = root / "benchmark.csv"
            with dataset.open("w", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=[
                        "ID",
                        "Target Identifier",
                        "Title query",
                        "Natural language query",
                        "Skip",
                        "Annotation",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "ID": "test",
                        "Target Identifier": json.dumps([{"entity_kname": "T.x0|thm"}]),
                        "Title query": "commutativity",
                        "Natural language query": "The sum,\nof two numbers commutes.",
                    }
                )
                writer.writerow({"ID": "skip", "Skip": "true", "Annotation": "fixture"})
            run(
                "benchmark",
                "-c",
                config_path,
                "-i",
                "plain",
                "-m",
                "metadata",
                "-f",
                dataset,
                "-s",
                "all",
                "-D",
                root / "reports",
            )
            outputs = list((root / "reports").glob("benchmark-*/*.json"))
            self.assertEqual(len(outputs), 12)
            for output in outputs:
                if not output.name.endswith(".run.json"):
                    data = json.loads(output.read_text())
                    self.assertEqual(
                        data["summary"]["all_queries"]["top_k_accuracy"]["average"], 1
                    )
                    self.assertEqual(
                        data["summary"]["all_queries"]["top_k_accuracy"]["sample_size"],
                        3,
                    )
                    self.assertTrue(data["skip"]["metadata"]["skipped"])
            run(
                "duplicates",
                "-c",
                config_path,
                "-i",
                "plain",
                "-e",
                "A",
                "-k",
                "all",
                "-x",
                "-D",
                root / "reports",
            )
            report = json.loads(
                next((root / "reports").glob("experiment_*.json")).read_text()
            )
            self.assertTrue(report["llm_judge"])
            for section in report["sections"].values():
                self.assertEqual(section["self_retrieval"]["failure_fraction"], 0)
                for entry in section["entries"]:
                    for item in entry["items"]:
                        self.assertTrue(
                            all(c["entry"] != "A" for c in item["candidates"])
                        )

    def test_registered_afp_build(self):
        afp = subprocess.check_output(
            ["isabelle", "getenv", "-b", "AFP_BASE"], text=True
        ).strip()
        if not afp:
            self.skipTest("No registered AFP available for session integration")
        components_base = subprocess.check_output(
            ["isabelle", "getenv", "-b", "ISABELLE_COMPONENTS_BASE"], text=True
        ).strip()
        with tempfile.TemporaryDirectory(prefix="isasearch-afp-") as temp:
            root = Path(temp)
            env = dict(
                os.environ, USER_HOME=str(root / "home"), ISASEARCH_TEST_KEY="test-key"
            )
            etc = root / "home/.isabelle/Isabelle2025-2/etc"
            etc.mkdir(parents=True)
            (etc / "components").write_text(str(ROOT / "isabelle") + "\n")
            (etc / "settings").write_text(
                f'ISABELLE_COMPONENTS_BASE="{components_base}"\n'
                'ISABELLE_TOOL_JAVA_OPTIONS="-Djava.awt.headless=true -Xms256m -Xmx4g -Xss16m"\n'
            )
            stub = Stub({})
            self.addCleanup(stub.close)
            config = {
                "embedding_backend": "openai",
                "openai_embedding_model": "fixture",
                "openai_embedding_base_url": stub.url + "/v1",
                "openai_base_url": stub.url + "/v1",
                "openai_api_key_env": "ISASEARCH_TEST_KEY",
                "llm_backend": "openai",
                "openai_document_model": "fixture",
                "enable_llm_output_cache": False,
                "prompts_folder": os.path.relpath(ROOT / "prompts/qwen3-gemma", root),
            }
            cfg = root / "config.json"
            cfg.write_text(json.dumps(config))

            def run(tool, *args, ok=True):
                result = subprocess.run(
                    [
                        "isabelle",
                        "isasearch_" + tool,
                        "-c",
                        str(cfg),
                        "-i",
                        "afp-test",
                        *map(str, args),
                    ],
                    env=env,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=240,
                )
                self.assertEqual(
                    result.returncode == 0, ok, result.stdout + result.stderr
                )
                return result

            missing = run("index", "Example-Submission", ok=False)
            self.assertIn("No registered AFP", missing.stderr)
            # Both registration forms must resolve the same AFP root.
            for registration in (Path(afp), Path(afp) / "thys"):
                (etc / "components").write_text(
                    str(registration) + "\n" + str(ROOT / "isabelle") + "\n"
                )
                run("index", "Example-Submission")
            descriptions = [
                call
                for call in stub.calls
                if "chat/completions" in call[0]
                and call[1]["messages"][0]["content"] != "Reply with OK."
            ]
            self.assertEqual(
                len(descriptions), 2, "Resumption regenerated unchanged descriptions"
            )
            found = json.loads(run("search", "truth").stdout)["results"]
            self.assertEqual(len(found), 2)
            self.assertTrue(
                all(d["entry"] == "Example-Submission" for d in found), found
            )
            run("index_build", "-D", root / "components")
            run(
                "duplicates",
                "-k",
                "theorems",
                "-e",
                "Example-Submission",
                "-J",
                "-D",
                root / "reports",
            )
            dataset = root / "benchmark.csv"
            with dataset.open("w", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=["ID", "Target Identifier", "Title query"]
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "ID": "truth",
                        "Target Identifier": json.dumps([{"id": found[0]["id"]}]),
                        "Title query": "truth",
                    }
                )
            run("benchmark", "-f", dataset, "-D", root / "reports")
            # Use an isolated AFP copy to exercise changed/deleted sources and failed-build resumption.
            copied_afp = root / "afp"
            (copied_afp / "etc").mkdir(parents=True)
            (copied_afp / "thys").mkdir()
            (copied_afp / "metadata/entries").mkdir(parents=True)
            (copied_afp / "metadata/entries/Example-Submission.toml").write_text(
                'title = "Metadata regression title"\n'
                'abstract = "Metadata regression abstract"\n'
            )
            for filename in ("settings", "version"):
                shutil.copyfile(
                    Path(afp) / "etc" / filename, copied_afp / "etc" / filename
                )
            shutil.copytree(
                Path(afp) / "thys/Example-Submission",
                copied_afp / "thys/Example-Submission",
            )
            (copied_afp / "thys/ROOTS").write_text("Example-Submission\n")
            (etc / "components").write_text(
                str(copied_afp) + "\n" + str(ROOT / "isabelle") + "\n"
            )
            config["embedding_attempts"] = 1
            cfg.write_text(json.dumps(config))
            run("index", "Example-Submission")
            # Only the flag changes: the base prompts folder remains configured.
            # Inspect actual LLM requests to ensure metadata reaches the model.
            calls_before = len(stub.calls)
            config["add_metadata"] = True
            cfg.write_text(json.dumps(config))
            run("index", "-i", "afp-metadata-test", "-n", "Example-Submission")
            metadata_prompts = [
                body["messages"][0]["content"]
                for path, body, _ in stub.calls[calls_before:]
                if "chat/completions" in path
                and body["messages"][0]["content"] != "Reply with OK."
            ]
            self.assertEqual(len(metadata_prompts), 2)
            for prompt in metadata_prompts:
                self.assertIn("Title: metadata regression title", prompt)
                self.assertIn("Abstract: metadata regression abstract", prompt)
            metadata_index = (
                root
                / "home/.isabelle/Isabelle2025-2/isasearch/indexes/afp-metadata-test"
            )
            generation = json.loads((metadata_index / "current.json").read_text())[
                "generation"
            ]
            manifest = json.loads(
                (metadata_index / generation / "manifest.json").read_text()
            )
            for corpus in manifest["corpora"]:
                self.assertTrue(corpus["recipe"]["add_metadata"])
                self.assertEqual(
                    corpus["recipe"]["prompts"]["describe"],
                    (
                        ROOT / "prompts/qwen3-gemma-with-metadata/describe.txt"
                    ).read_text(),
                )
            config.pop("add_metadata")
            cfg.write_text(json.dumps(config))
            theory = copied_afp / "thys/Example-Submission/Submission.thy"
            original = theory.read_text()
            theory.write_text(
                original.rsplit("end", 1)[0] + 'lemma added_fact: "True" by simp\nend\n'
            )
            stub.fail_input_contains = "added_fact"
            run("index", "Example-Submission", ok=False)
            self.assertEqual(
                len(json.loads(run("search", "truth").stdout)["results"]), 2
            )
            descriptions_before = sum(
                "chat/completions" in path
                and body["messages"][0]["content"] != "Reply with OK."
                for path, body, _ in stub.calls
            )
            stub.fail_input_contains = ""
            run("index", "-n", "Example-Submission")
            self.assertEqual(
                len(json.loads(run("search", "truth").stdout)["results"]), 3
            )
            descriptions_after = sum(
                "chat/completions" in path
                and body["messages"][0]["content"] != "Reply with OK."
                for path, body, _ in stub.calls
            )
            self.assertEqual(
                descriptions_before,
                descriptions_after,
                "Saved description was not reused after embedding failure",
            )
            theory.write_text(
                theory.read_text().replace(
                    'added_fact: "True"', r'added_fact: "True \<and> True"'
                )
            )
            run("index", "Example-Submission")
            changed = json.loads(run("search", "truth").stdout)["results"]
            self.assertTrue(any("True ∧ True" in d["src"] for d in changed))
            theory.write_text(original)
            run("index", "Example-Submission")
            self.assertEqual(
                len(json.loads(run("search", "truth").stdout)["results"]), 2
            )
            # Removing all selected facts is guarded, and cannot replace the published generation.
            config["solr_query"] = "id:does-not-exist"
            cfg.write_text(json.dumps(config))
            pruned = run("index", "-n", "Example-Submission", ok=False)
            self.assertIn("Refusing to prune", pruned.stderr)
            self.assertEqual(
                len(json.loads(run("search", "truth").stdout)["results"]), 2
            )


if __name__ == "__main__":
    unittest.main()
