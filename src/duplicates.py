"""
duplicates.py: This file finds material of an AFP entry that already exists elsewhere in the Archive
of Formal Proofs. It was written for the experiment proposed by an AFP maintainer: take the n newest
AFP entries, search for their definitions in the AFP and ignore the definitions of the entry itself.

The analysis works entirely on the corpora that are already built by src/bootstrap.py, i.e. no
re-indexing and no separate ingestion of a submission is required. For every document of an analysed
entry the following steps are performed:

1. The document is turned into the very same embedding string that the corpus side uses
   (see document_embedding_string in src/embeddings.py) and queried against the ChromaDB collection.
2. Before anything is filtered, the rank and the distance at which the document retrieves itself are
   recorded. This is a positive control that requires no ground truth: a document must always find
   itself at a distance of about 0.
3. All candidates belonging to the analysed entry are removed, which implements the "ignore the
   definitions in the entry itself" part of the experiment.
4. Every remaining candidate gets a syntactic similarity score and, if enabled, a verdict of the
   configured LLM. Distance, syntactic similarity and verdict together decide the reported tier.

The result is a Markdown report for human inspection plus a JSON report with all raw numbers.
Semantic similarity is not logical duplication, so the tiers are a triage aid and not a verdict.
"""

import argparse
import difflib
import glob
import json
import os
import re
import sys
import time
import tomllib

from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from src.bootstrap import (
    load_config,
    boot_components,
    prepare_corpus_sources,
    DEFINITIONS_BUILD,
    DEFINITIONS_LOAD,
)
from src.documents import strip_proof
from src.embeddings import (
    document_embedding_string,
    add_doc_urls,
    embedding_model_name,
)
from src.llm import save_llm_output_cache, query_model_name
from src.solr import docs_by_ids


# Every AFP document ID contains the path of its theory file, so the entry a document belongs to is
# the first path segment after "/thys/". This is used both to select the documents of an entry and to
# exclude an entry from its own search results.
ENTRY_PATH_MARKER = "/thys/"

KIND_DEFINITIONS = "definitions"
KIND_THEOREMS = "theorems"
KINDS = [KIND_DEFINITIONS, KIND_THEOREMS]

# The LLM output cache of the duplicate detection, overridable through config["dedup_llm_cache"].
# It is deliberately not the cache of the web application: both rewrite their cache as a whole, so
# one shared file would lose everything the other one cached since it started. The two never share
# an entry anyway, because the judge prompt differs from every prompt the application uses.
DEDUP_LLM_CACHE = "llm_output_cache_dedup.json"


def dedup_llm_cache_name(config):
    return config.get("dedup_llm_cache", DEDUP_LLM_CACHE)


VERDICTS = ["DUPLICATE", "VARIANT", "RELATED", "DIFFERENT"]
UNKNOWN_VERDICT = "UNKNOWN"

TIER_NEAR_EXACT = "near-exact"
TIER_LIKELY = "likely"
TIER_POSSIBLE = "possible"
# Ordered from the strongest to the weakest tier.
TIERS = [TIER_NEAR_EXACT, TIER_LIKELY, TIER_POSSIBLE]

# Two documents of different entries that define a constant or type of the same base name and whose
# sources are this similar are treated as a duplicate pair, i.e. as a synthetic ground truth.
GROUND_TRUTH_SYNTACTIC_THRESHOLD = 0.85
# Base names such as "empty" or "size" are defined by a lot of entries. Comparing every pair of a very
# large group is quadratic and yields no useful ground truth, so such groups are skipped.
GROUND_TRUTH_MAX_GROUP_SIZE = 50

# If more than this fraction of the analysed documents does not retrieve itself, something in the
# pipeline is broken (e.g. the corpus was embedded with a different prompt or embedder).
SELF_RETRIEVAL_FAILURE_LIMIT = 0.05

# Upper bound for the number of ChromaDB results that are requested per document and for the number
# of values of a single ChromaDB response, so that the response size stays bounded for large entries.
MAX_EXTRA_RESULTS = 300
MAX_RESPONSE_VALUES = 10000

# Isabelle commands that may start the source code of a document. They are removed before comparing
# two sources syntactically, because the command itself carries no mathematical content.
COMMANDS_PATTERN = (
    "definition|abbreviation|fun|function|primrec|primcorec|datatype|codatatype|"
    "record|type_synonym|typedef|inductive_set|inductive|coinductive|"
    "theorem|lemma|corollary|proposition|schematic_goal"
)
LEADING_COMMAND = re.compile(r"^\s*(?:" + COMMANDS_PATTERN + r")\b")
# A name label such as 'foo:' or 'foo [simp]:'. The negative lookahead keeps the type ascription of a
# definition ('foo :: "nat ⇒ nat"') intact, because that is part of the mathematical content.
LEADING_NAME = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_'.]*\s*(?:\[[^\]]*\])?\s*:(?!:)")

# A statement this short carries no mathematical content anymore. This happens if the source starts
# with something that strip_proof or the patterns above cut away, e.g. a quoted 'proof' token, and
# two such statements would otherwise compare as identical.
MIN_STATEMENT_LENGTH = 8


# Return the AFP entry a document ID belongs to, or None for documents outside of the AFP
# (i.e. built-in Isabelle theories, whose IDs start with ISABELLE_HOME).
def entry_of_id(doc_id):
    parts = doc_id.split(ENTRY_PATH_MARKER)

    if len(parts) < 2:
        return None

    return parts[1].split("/")[0]


# Reduce the source code of a document to the part that carries mathematical content, i.e. drop the
# proof, the leading command, an optional name label and any difference in whitespace.
def normalized_statement(src):
    statement = strip_proof(src)
    statement = LEADING_COMMAND.sub(" ", statement, count=1)
    statement = LEADING_NAME.sub(" ", statement, count=1)

    return re.sub(r"\s+", " ", statement).strip()


# Similarity of two sources between 0.0 and 1.0, based on their normalized statements only.
# This is a purely syntactic signal that complements the semantic distance of the embeddings.
def syntactic_similarity(a_src, b_src):
    a_statement = normalized_statement(a_src)
    b_statement = normalized_statement(b_src)

    # difflib reports a ratio of 1.0 for two empty strings, and a very high one for two statements
    # that are only a quote character. Both would be false duplicates.
    if (
        len(a_statement) < MIN_STATEMENT_LENGTH
        or len(b_statement) < MIN_STATEMENT_LENGTH
    ):
        return 0.0

    return difflib.SequenceMatcher(None, a_statement, b_statement).ratio()


# The part of the source code that is shown to the LLM, cut like in generate_document_descriptions
# (src/documents.py), so that the judge sees the same statement that was informalized.
def statement_excerpt(src, max_length):
    return strip_proof(src)[:max_length].strip()


# Read the submission date of every AFP entry from afp/metadata/entries/<entry>.toml.
def entry_dates(config):
    metadata_folder = config["components"]["afp"]["local_folder"] + "/metadata/entries"
    dates = {}
    without_date = []

    for path in sorted(glob.glob(metadata_folder + "/*.toml")):
        entry = Path(path).stem

        try:
            with open(path, "rb") as file:
                toml = tomllib.load(file)
        except Exception:
            print(f"Warning: failed loading {path}, thus skipping entry {entry}.")
            continue

        date = toml.get("date")

        if date is None:
            without_date.append(entry)
            continue

        # tomllib returns a datetime.date, whose ISO representation sorts chronologically.
        dates[entry] = str(date)

    if len(without_date) > 0:
        print(
            f"Warning: {len(without_date)} entries have no 'date' in their metadata file "
            "and are therefore not considered when selecting the newest entries."
        )

    return dates


# Select the 'count' newest AFP entries that are actually part of the corpus. Entries that are newer
# but not indexed are skipped, which is the normal case as long as only a few sessions are indexed.
def newest_entries(config, count, available_entries):
    dates = entry_dates(config)
    ranked = sorted(dates.items(), key=lambda item: (item[1], item[0]), reverse=True)

    selected = []
    skipped = []

    for entry, date in ranked:
        if len(selected) >= count:
            break

        if entry in available_entries:
            selected.append({"entry": entry, "date": date})
        else:
            skipped.append(entry)

    if len(skipped) > 0:
        print(
            f"Warning: skipped {len(skipped)} newer entries that are not part of the corpus "
            f"(e.g. {', '.join(skipped[:5])}). Only indexed sessions can be analysed."
        )

    return selected


# All documents of the corpus that belong to the given entry, ordered by their ID for reproducibility.
def entry_docs(index, entry):
    return [index[doc_id] for doc_id in sorted(index) if entry_of_id(doc_id) == entry]


# All entries that occur in the corpus.
def entries_in_index(index):
    entries = set()

    for doc_id in index:
        entry = entry_of_id(doc_id)

        if entry is not None:
            entries.add(entry)

    return entries


# Query every target with every given document and return, per document, the rank at which it
# retrieved itself (positive control) and the best candidates outside of the excluded entry.
#
# 'targets' is a list of (kind, collection, corpus_index) tuples. With a single target this behaves
# exactly like searching one corpus. With both targets a document is matched against definitions and
# theorems at once, which is sound because both collections are filled by get_chromadb_collection
# with the same embedder and the same 'embed' prompt (see document_embedding_string) into the same
# cosine space, so their distances are directly comparable and can be merged into one ranking.
#
# 'home_kind' names the target the query documents themselves live in. The positive control is taken
# from that target's own ranking only: on the merged ranking a cross kind near twin could outrank the
# document itself, which would look like a broken embedding space although nothing is wrong.
def find_candidates(targets, prompts, query_docs, exclude_entry, home_kind, config):
    top_k = config["dedup_top_k"]
    sizes = {}
    n_results = {}

    for kind, collection, corpus_index in targets:
        sizes[kind] = collection.count()

        if sizes[kind] == 0:
            raise RuntimeError(
                f"The ChromaDB collection for {kind} is empty. Build the corpus first "
                "(python3 -m src.duplicates --build-corpus-only)."
            )

        # Every document of the analysed entry may rank above the first candidate of another entry,
        # so enough results have to be requested to still have 'top_k' candidates left after the
        # exclusion. How many that is depends on how many documents the entry has in *this* corpus,
        # which is not the number of query documents: when a definition is matched against the
        # theorems corpus, the theorems of the same entry are excluded as well and there are usually
        # far more of them. The number of requested results is capped, so that the size of a single
        # response stays bounded.
        entry_size = len(entry_docs(corpus_index, exclude_entry))
        n_results[kind] = min(
            sizes[kind], top_k + min(entry_size, MAX_EXTRA_RESULTS) + 1
        )

    chunk_size = max(1, min(100, MAX_RESPONSE_VALUES // sum(n_results.values())))

    analyses = []
    # Per corpus, the number of documents for which the requested results were completely used up by
    # the documents of the analysed entry, so that duplicates ranked below them could not be seen.
    truncated = {kind: 0 for kind in n_results}
    stale = 0

    for i in tqdm(range(0, len(query_docs), chunk_size)):
        batch = query_docs[i : i + chunk_size]
        query_texts = [document_embedding_string(doc, prompts) for doc in batch]
        responses = {
            kind: collection.query(query_texts=query_texts, n_results=n_results[kind])
            for kind, collection, _ in targets
        }

        for j, doc in enumerate(batch):
            self_rank = None
            self_distance = None
            hits = []

            for kind, _, corpus_index in targets:
                response = responses[kind]
                returned = 0
                survived = 0

                for position, (metadata, distance) in enumerate(
                    zip(response["metadatas"][j], response["distances"][j]), start=1
                ):
                    returned += 1
                    candidate_id = metadata["source"]

                    # The document itself is the positive control and never a candidate.
                    if candidate_id == doc["id"]:
                        if kind == home_kind:
                            self_rank = position
                            self_distance = distance
                        continue

                    if (
                        exclude_entry is not None
                        and entry_of_id(candidate_id) == exclude_entry
                    ):
                        continue

                    # A collection is only ever added to, so it can still contain documents of an
                    # older version of the corpus. Those cannot be reported, because neither their
                    # source code nor their metadata is available anymore.
                    if candidate_id not in corpus_index:
                        stale += 1
                        continue

                    survived += 1
                    hits.append(
                        {"id": candidate_id, "distance": distance, "kind": kind}
                    )

                # If this corpus returned everything that was asked of it and still did not yield
                # 'top_k' usable candidates, the requested window was too small and duplicates that
                # rank below the documents of the entry itself were not seen. If the window covers
                # the whole collection there is nothing below it, so nothing was missed.
                if (
                    survived < top_k
                    and returned >= n_results[kind]
                    and n_results[kind] < sizes[kind]
                ):
                    truncated[kind] += 1

            # Merging the targets by ascending distance keeps the ranking of a single target intact.
            hits.sort(key=lambda hit: hit["distance"])
            candidates = hits[:top_k]

            analyses.append(
                {
                    "doc": doc,
                    "exclude_entry": exclude_entry,
                    "self_rank": self_rank,
                    "self_distance": self_distance,
                    "candidates": candidates,
                }
            )

    if stale > 0:
        print(
            f"Warning: ignored {stale} results that are in the ChromaDB collection but not in the "
            "document index. The collection contains documents of an older version of the corpus. "
            "Delete the ChromaDB collection to get rid of them."
        )

    for kind, count in truncated.items():
        if count > 0:
            print(
                f"Warning: for {count} documents the closest {n_results[kind]} results of the "
                f"{kind} corpus did not contain {top_k} usable candidates, because they were used "
                "up by the documents of the analysed entry itself. Duplicates that rank below "
                f"those can be missed. This happens when the entry has more than "
                f"{MAX_EXTRA_RESULTS} documents in that corpus."
            )

    return analyses


# Add the syntactic similarity of every candidate to its query document.
def add_syntactic_similarity(analyses, corpus_index):
    for analysis in analyses:
        for candidate in analysis["candidates"]:
            candidate_doc = corpus_index.get(candidate["id"])

            if candidate_doc is None:
                candidate["syntactic_similarity"] = 0.0
                continue

            candidate["syntactic_similarity"] = syntactic_similarity(
                analysis["doc"]["src"], candidate_doc["src"]
            )


# Extract the verdict and its justification from the raw LLM output.
def parse_verdict(raw_output):
    text = raw_output

    if "<BEGIN>" in text:
        text = text.split("<BEGIN>", 1)[1]
    if "<END>" in text:
        text = text.split("<END>", 1)[0]

    text = text.strip()
    match = re.search(r"VERDICT\s*:\s*([A-Za-z]+)", text)

    if match is None:
        return UNKNOWN_VERDICT, text[:300]

    verdict = match.group(1).upper()

    if verdict not in VERDICTS:
        return UNKNOWN_VERDICT, text[:300]

    return verdict, text[match.end() :].strip()[:300]


# Let the configured LLM decide whether a query document and a candidate are duplicates.
# Only the closest candidates of every document are judged, so the number of LLM calls stays bounded.
# Judgements are stored in the existing LLM output cache, which makes repeated runs free.
def judge_candidates(
    model, prompts, config, analyses, corpus_index, llm_output_cache, save_every=50
):
    max_per_item = config["dedup_max_judged_per_item"]
    distance_threshold = config["dedup_distance_threshold"]
    max_length = config["theorem_max_length"]
    model_key = query_model_name(config)

    # If the LLM output cache is disabled, llm_output_cache is None. Use a local dictionary in that
    # case, so a pair that shows up twice within one run is still only judged once.
    cache = llm_output_cache if llm_output_cache is not None else {}

    pending = []

    for analysis in analyses:
        for candidate in analysis["candidates"][:max_per_item]:
            # Candidates are ordered by ascending distance, so everything after the first candidate
            # above the threshold is above the threshold as well.
            if candidate["distance"] > distance_threshold:
                break

            if candidate["id"] in corpus_index:
                pending.append((analysis, candidate))

    print(f"Judging {len(pending)} candidate pairs with the LLM...")

    unsaved = 0

    for analysis, candidate in tqdm(pending):
        prompt = prompts["duplicate_judge"].format(
            item_a=statement_excerpt(analysis["doc"]["src"], max_length),
            item_b=statement_excerpt(corpus_index[candidate["id"]]["src"], max_length),
        )

        cached = cache.get(model_key, {}).get(prompt)

        if cached is not None:
            raw_output = cached["output"]
        else:
            start = time.time()
            raw_output = model.generate(prompt)

            if model_key not in cache:
                cache[model_key] = {}

            cache[model_key][prompt] = {
                "output": raw_output,
                "output_duration": time.time() - start,
            }
            unsaved += 1

            # Writing the whole cache after every single judgement would dominate the runtime, so it
            # is written in batches instead.
            if config["enable_llm_output_cache"] and unsaved >= save_every:
                save_llm_output_cache(cache, config, dedup_llm_cache_name(config))
                unsaved = 0

        verdict, justification = parse_verdict(raw_output)
        candidate["verdict"] = verdict
        candidate["justification"] = justification

    if config["enable_llm_output_cache"] and unsaved > 0:
        save_llm_output_cache(cache, config, dedup_llm_cache_name(config))


# Decide how strong the evidence for a candidate being a duplicate is, or return None if the
# candidate is not worth reporting at all.
def classify(candidate, config):
    if (
        candidate["distance"] <= config["dedup_strong_distance_threshold"]
        or candidate["syntactic_similarity"] >= config["dedup_syntactic_threshold"]
    ):
        return TIER_NEAR_EXACT

    if candidate.get("verdict") == "DUPLICATE":
        return TIER_LIKELY

    if candidate["distance"] <= config["dedup_distance_threshold"]:
        return TIER_POSSIBLE

    return None


# Assign a tier to every candidate and return the strongest tier per analysed document.
def classify_analyses(analyses, config):
    for analysis in analyses:
        tiers = []

        for candidate in analysis["candidates"]:
            candidate["tier"] = classify(candidate, config)

            if candidate["tier"] is not None:
                tiers.append(candidate["tier"])

        analysis["best_tier"] = next(
            (tier for tier in TIERS if tier in tiers),
            None,
        )


# The base names of all constants and types a document defines, e.g. "Ramsey.part" becomes "part".
def defined_base_names(doc):
    names = set()

    for qualified in list(doc.get("consts", [])) + list(doc.get("typs", [])):
        base = str(qualified).split(".")[-1]

        if base != "":
            names.add(base)

    return names


# Derive a synthetic ground truth without using the semantic search: two documents of different
# entries that define something of the same base name and whose sources are nearly identical are
# almost certainly duplicates. The semantic search should find those, which gives a recall number.
# This is biased towards textual duplicates, so it is a lower bound and not a measure of semantic
# retrieval quality.
def synthetic_ground_truth(index):
    by_name = {}

    for doc_id, doc in index.items():
        if entry_of_id(doc_id) is None:
            continue

        for name in defined_base_names(doc):
            by_name.setdefault(name, []).append(doc)

    duplicates = {}
    skipped_groups = 0

    for docs in by_name.values():
        if len(docs) < 2:
            continue

        if len(docs) > GROUND_TRUTH_MAX_GROUP_SIZE:
            skipped_groups += 1
            continue

        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                a = docs[i]
                b = docs[j]

                if entry_of_id(a["id"]) == entry_of_id(b["id"]):
                    continue

                if (
                    syntactic_similarity(a["src"], b["src"])
                    >= GROUND_TRUTH_SYNTACTIC_THRESHOLD
                ):
                    duplicates.setdefault(a["id"], set()).add(b["id"])
                    duplicates.setdefault(b["id"], set()).add(a["id"])

    return duplicates, skipped_groups


# Fraction of the analysed documents that have a known duplicate outside of their own entry and
# actually retrieved at least one of them within the top k candidates.
def recall_at_k(ground_truth, analyses):
    considered = 0
    recovered = 0

    for analysis in analyses:
        expected = ground_truth.get(analysis["doc"]["id"])

        if expected is None:
            continue

        # Duplicates inside the analysed entry itself are excluded from the results by design and
        # therefore cannot be recovered.
        reachable = {
            doc_id
            for doc_id in expected
            if entry_of_id(doc_id) != analysis["exclude_entry"]
        }

        if len(reachable) == 0:
            continue

        considered += 1

        if len(reachable & {c["id"] for c in analysis["candidates"]}) > 0:
            recovered += 1

    return {
        "documents_with_known_duplicate": considered,
        "documents_recovered": recovered,
        "recall": (recovered / considered) if considered > 0 else None,
    }


# Build the links of every document that appears in the report. Definitions carry the required Solr
# keys in the corpus already, everything else (e.g. theorems) is looked up in Solr once.
def resolve_urls(doc_ids, corpus_index, solr, config):
    documents = {}

    for doc_id in doc_ids:
        doc = corpus_index.get(doc_id)

        if doc is not None:
            documents[doc_id] = {
                "id": doc_id,
                "file": doc.get("file"),
                "url_path": doc.get("url_path"),
                "start_line": doc.get("start_line"),
            }

    missing = [
        doc_id
        for doc_id, doc in documents.items()
        if doc["file"] is None or doc["url_path"] is None
    ]

    if len(missing) > 0:
        print(f"Looking up {len(missing)} documents in Solr to build links...")

        for solr_doc in docs_by_ids(solr, missing):
            doc = documents.get(solr_doc["id"])

            if doc is None:
                continue

            doc["file"] = solr_doc.get("file")
            doc["url_path"] = solr_doc.get("url_path")
            doc["start_line"] = solr_doc.get("start_line")

    urls = {}

    for doc_id, doc in documents.items():
        if doc["file"] is None or doc["url_path"] is None:
            urls[doc_id] = {"remote_url": "#", "entry_url": "#", "theory_url": "#"}
        else:
            resolved = add_doc_urls(doc, config)
            urls[doc_id] = {
                "remote_url": resolved["remote_url"],
                "entry_url": resolved["entry_url"],
                "theory_url": resolved["theory_url"],
            }

    return urls


# Analyse a single entry, i.e. match every document of the entry that is of the home kind against
# every target corpus. 'home_index' is the corpus the query documents are taken from and
# 'lookup_index' resolves candidates of any target.
def analyse_entry(entry, home_index, lookup_index, targets, home_kind, prompts, config):
    query_docs = entry_docs(home_index, entry)

    if len(query_docs) == 0:
        print(f"Warning: entry {entry} has no documents in this corpus, thus skipping.")
        return None

    print(f"Analysing {len(query_docs)} documents of entry {entry}...")
    analyses = find_candidates(targets, prompts, query_docs, entry, home_kind, config)
    add_syntactic_similarity(analyses, lookup_index)

    return analyses


# A document passes the positive control if it retrieved itself at a distance of about 0. Demanding
# rank 1 alone would be wrong: if the analysed entry really is a copy of an archived one, the copy
# sits at the same place in the embedding space and the order between the two is arbitrary.
def self_retrieval_passed(analysis, config):
    if analysis["self_rank"] is None:
        return False

    return (
        analysis["self_rank"] == 1
        or analysis["self_distance"] <= config["dedup_strong_distance_threshold"]
    )


# Summarize the positive control, i.e. how often a document retrieved itself at a distance of about 0.
def self_retrieval_summary(analyses, config):
    distances = [
        analysis["self_distance"]
        for analysis in analyses
        if analysis["self_distance"] is not None
    ]
    failures = [
        {
            "id": analysis["doc"]["id"],
            "self_rank": analysis["self_rank"],
            "self_distance": analysis["self_distance"],
        }
        for analysis in analyses
        if not self_retrieval_passed(analysis, config)
    ]
    analysed = len(analyses)

    return {
        "documents": analysed,
        "self_retrieved": analysed - len(failures),
        "failure_fraction": (len(failures) / analysed) if analysed > 0 else 0.0,
        "mean_self_distance": (sum(distances) / len(distances))
        if len(distances) > 0
        else None,
        "failures": failures[:20],
    }


# Aggregate numbers over all analysed documents of one kind.
def aggregate(analyses, config):
    buckets = [0.05, 0.1, 0.2, 0.3, 0.5, 1.0]
    histogram = {f"<= {bucket}": 0 for bucket in buckets}
    histogram["> 1.0"] = 0

    tier_counts = {tier: 0 for tier in TIERS}
    tier_counts["none"] = 0
    verdict_counts = {verdict: 0 for verdict in VERDICTS}
    verdict_counts[UNKNOWN_VERDICT] = 0
    candidate_kind_counts = {kind: 0 for kind in KINDS}
    overlapping_entries = {}

    for analysis in analyses:
        if analysis["best_tier"] is None:
            tier_counts["none"] += 1
        else:
            tier_counts[analysis["best_tier"]] += 1

        if len(analysis["candidates"]) > 0:
            top_distance = analysis["candidates"][0]["distance"]

            for bucket in buckets:
                if top_distance <= bucket:
                    histogram[f"<= {bucket}"] += 1
                    break
            else:
                histogram["> 1.0"] += 1

        for candidate in analysis["candidates"]:
            if "verdict" in candidate:
                verdict_counts[candidate["verdict"]] += 1

            if candidate["tier"] is not None:
                candidate_kind_counts[candidate["kind"]] += 1
                candidate_entry = entry_of_id(candidate["id"])

                if candidate_entry is not None:
                    overlapping_entries[candidate_entry] = (
                        overlapping_entries.get(candidate_entry, 0) + 1
                    )

    flagged = tier_counts[TIER_NEAR_EXACT] + tier_counts[TIER_LIKELY]

    return {
        "documents": len(analyses),
        "documents_with_near_exact_or_likely_duplicate": flagged,
        "tier_counts": tier_counts,
        "verdict_counts": verdict_counts,
        "candidate_kind_counts": candidate_kind_counts,
        "top_1_distance_histogram": histogram,
        "overlapping_entries": dict(
            sorted(overlapping_entries.items(), key=lambda item: -item[1])[:20]
        ),
        "thresholds": {
            "top_k": config["dedup_top_k"],
            "distance": config["dedup_distance_threshold"],
            "strong_distance": config["dedup_strong_distance_threshold"],
            "syntactic": config["dedup_syntactic_threshold"],
        },
    }


# Decide which documents and candidates end up in the report. By default only candidates that reach
# a tier are reported, with 'report_all' every analysed document and every candidate is reported.
def is_reported(analysis, report_all):
    if report_all:
        return len(analysis["candidates"]) > 0

    return analysis["best_tier"] is not None


def is_reported_candidate(candidate, report_all):
    return report_all or candidate["tier"] is not None


# Convert the in-memory analyses into the plain data that is written to the JSON report.
def analyses_to_report(
    analyses, corpus_index, urls, report_all=False, source_excerpt_length=600
):
    items = []

    for analysis in analyses:
        if not is_reported(analysis, report_all):
            continue

        doc = analysis["doc"]
        candidates = []

        for candidate in analysis["candidates"]:
            if not is_reported_candidate(candidate, report_all):
                continue

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


# Return the (kind, collection, index) target of one kind.
def corpus_target(kind, components):
    if kind == KIND_DEFINITIONS:
        return kind, components["definition_collection"], components["definition_index"]

    return kind, components["collection"], components["document_index"]


# Run the analysis for one kind of document (definitions or theorems) over all selected entries.
# The query documents are always of the given kind. With 'cross' enabled they are matched against
# both corpora, so a definition can also find a theorem that states the same thing and vice versa.
def analyse_kind(
    kind, selected, components, config, use_llm_judge, report_all=False, cross=False
):
    home_kind, collection, home_index = corpus_target(kind, components)
    targets = [(home_kind, collection, home_index)]

    if cross:
        other_kind = KIND_THEOREMS if kind == KIND_DEFINITIONS else KIND_DEFINITIONS
        targets.append(corpus_target(other_kind, components))

    # Candidates can come from any target, so they are resolved against all of them. Merging the
    # indexes is safe because config["solr_query"] and config["solr_query_definitions"] select
    # disjoint Isabelle commands, so no document can be part of both corpora.
    lookup_index = dict(home_index)

    for _, _, index in targets[1:]:
        overlap = len(lookup_index) + len(index)
        lookup_index.update(index)

        if len(lookup_index) != overlap:
            print(
                "Warning: the theorem and the definition corpus share documents. Check that "
                "config['solr_query'] and config['solr_query_definitions'] do not overlap."
            )

    all_analyses = []
    entry_sections = []

    for selection in selected:
        analyses = analyse_entry(
            selection["entry"],
            home_index,
            lookup_index,
            targets,
            home_kind,
            components["prompts"],
            config,
        )

        if analyses is None:
            continue

        selection["analyses"] = analyses
        all_analyses.extend(analyses)

    if len(all_analyses) == 0:
        return None

    if use_llm_judge:
        judge_candidates(
            components["model"],
            components["prompts"],
            config,
            all_analyses,
            lookup_index,
            components["llm_output_cache"],
        )
    else:
        print(
            "LLM judging is disabled, thus only distance and syntactic similarity are used."
        )

    classify_analyses(all_analyses, config)

    # The synthetic ground truth is derived from the home corpus only. It groups documents by the
    # constants and types they define, which only the definitions corpus stores, so for theorems it
    # is empty by construction and the report suppresses the section.
    print("Deriving a synthetic ground truth from the corpus...")
    ground_truth, skipped_groups = synthetic_ground_truth(home_index)

    # Collect every document that shows up in the report, so its links are resolved in one go.
    reported_ids = set()
    for analysis in all_analyses:
        if not is_reported(analysis, report_all):
            continue

        reported_ids.add(analysis["doc"]["id"])

        for candidate in analysis["candidates"]:
            if is_reported_candidate(candidate, report_all):
                reported_ids.add(candidate["id"])

    urls = resolve_urls(sorted(reported_ids), lookup_index, components["solr"], config)

    for selection in selected:
        analyses = selection.get("analyses")

        if analyses is None:
            continue

        entry_sections.append(
            {
                "entry": selection["entry"],
                "date": selection["date"],
                "documents": len(analyses),
                "items": analyses_to_report(
                    analyses, lookup_index, urls, report_all=report_all
                ),
            }
        )
        # The analyses are only needed while building this section.
        del selection["analyses"]

    return {
        "entries": entry_sections,
        "aggregates": aggregate(all_analyses, config),
        "self_retrieval": self_retrieval_summary(all_analyses, config),
        "synthetic_ground_truth": {
            **recall_at_k(ground_truth, all_analyses),
            "skipped_groups": skipped_groups,
        },
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m src.duplicates",
        description=(
            "Find material of AFP entries that already exists elsewhere in the Archive of Formal "
            "Proofs. By default the newest indexed entries are analysed."
        ),
    )
    parser.add_argument(
        "--newest",
        type=int,
        default=10,
        help="number of newest AFP entries to analyse (default: 10)",
    )
    parser.add_argument(
        "--entry",
        action="append",
        default=None,
        metavar="NAME",
        help="analyse this entry instead of the newest ones, may be given multiple times",
    )
    parser.add_argument(
        "--kinds",
        default=KIND_DEFINITIONS,
        help=(
            "comma separated list of the kinds of documents to analyse, "
            f"any of {', '.join(KINDS)}, or 'all' for both (default: {KIND_DEFINITIONS})"
        ),
    )
    parser.add_argument(
        "--cross",
        action="store_true",
        help=(
            "match every analysed document against the definitions and the theorems corpus, so a "
            "definition can also find a theorem that states the same thing and vice versa"
        ),
    )
    parser.add_argument(
        "--all-candidates",
        action="store_true",
        help=(
            "report the closest candidates of every analysed document, instead of only those that "
            "reach one of the tiers. Useful to inspect the raw search results."
        ),
    )
    parser.add_argument(
        "--build-corpus-only",
        action="store_true",
        help="only build the corpora (including the LLM descriptions) and exit",
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help=(
            "only install or update the components and build the FindFacts index, then exit. This "
            "is the part of a build that requires Solr to be stopped, because the indexer writes "
            "the same index a running Solr holds open. Run it first, then start Solr and run "
            "--build-corpus-only for the rest."
        ),
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help=(
            "run strictly read-only against corpora that were already built, so that this run can "
            "happen while the web application is up. Nothing is fetched, described, embedded or "
            "pruned; use it for every analysis on a deployed server."
        ),
    )
    parser.add_argument(
        "--no-llm-judge",
        action="store_true",
        help="do not let the LLM judge the closest candidates, overrides config['dedup_llm_judge']",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help="folder the report is written to, overrides config['dedup_report_folder']",
    )

    args = parser.parse_args(argv)

    if args.kinds.strip() == "all":
        args.kinds = list(KINDS)
    else:
        args.kinds = [
            kind.strip() for kind in args.kinds.split(",") if kind.strip() != ""
        ]

    for kind in args.kinds:
        if kind not in KINDS:
            parser.error(f"unknown kind '{kind}', expected any of {', '.join(KINDS)}")

    if len(args.kinds) == 0:
        parser.error("at least one kind has to be given")

    if args.newest < 1:
        parser.error("--newest has to be at least 1")

    if args.serve and args.build_corpus_only:
        parser.error(
            "--serve and --build-corpus-only contradict each other, because building the corpora "
            "is exactly what --serve forbids"
        )

    if args.serve and args.index_only:
        parser.error(
            "--serve and --index-only contradict each other, because building the FindFacts index "
            "is exactly what --serve forbids"
        )

    return args


def main(argv=None):
    args = parse_args(argv)
    config = load_config()

    # Done before boot_components, because the FindFacts index has to be built while Solr is down
    # and every later step needs Solr up. It also skips the LLM and embedding backend checks, which
    # a pure indexing run has no use for.
    if args.index_only:
        prepare_corpus_sources(config)
        print("Finished building the FindFacts index.")
        return 0

    # Cross-kind matching queries the other corpus as well, so both are needed for it. Loading a
    # corpus that is never queried would cost gigabytes of memory on the full AFP, thus each one is
    # only loaded when this run actually reaches it.
    #
    # --build-corpus-only is the exception: it is the build step of a deployment and therefore has to
    # produce everything the web application later serves, not only the corpus of the analysed kind.
    needs_definitions = (
        KIND_DEFINITIONS in args.kinds or args.cross or args.build_corpus_only
    )
    needs_theorems = KIND_THEOREMS in args.kinds or args.cross or args.build_corpus_only

    if needs_definitions:
        definitions = DEFINITIONS_LOAD if args.serve else DEFINITIONS_BUILD
    else:
        definitions = None

    components = boot_components(
        config,
        serve=args.serve,
        theorems=needs_theorems,
        definitions=definitions,
        # The web application rewrites its own cache as a whole, so sharing one file with it would
        # make whichever process saves last drop the other's entries.
        llm_cache_name=dedup_llm_cache_name(config),
    )

    if needs_definitions and components["definition_index"] is None:
        print(
            "The definitions corpus is not available. Build it with "
            "'python3 -m src.duplicates --build-corpus-only' first."
        )
        return 1

    if args.build_corpus_only:
        print("Finished building the corpora.")
        return 0

    use_llm_judge = config["dedup_llm_judge"] and not args.no_llm_judge
    report_folder = (
        args.report_dir
        if args.report_dir is not None
        else config["dedup_report_folder"]
    )

    # The entries are selected on the corpus of the first requested kind, so that every analysed
    # entry actually has documents of the kind the experiment is about.
    primary_index = (
        components["definition_index"]
        if args.kinds[0] == KIND_DEFINITIONS
        else components["document_index"]
    )
    available_entries = entries_in_index(primary_index)

    if args.entry is not None:
        selected = []
        # Read the dates once, because every call parses the metadata file of every AFP entry.
        dates = entry_dates(config)

        for entry in args.entry:
            if entry not in available_entries:
                print(
                    f"Warning: entry {entry} is not part of the corpus, thus skipping it."
                )
                continue

            selected.append({"entry": entry, "date": dates.get(entry)})
    else:
        selected = newest_entries(config, args.newest, available_entries)

    if len(selected) == 0:
        print(
            "No entry could be analysed. Only entries of indexed sessions "
            f"(config['isabelle_sessions'] = {config['isabelle_sessions']}) are available."
        )
        return 1

    print(f"Analysing entries: {', '.join(s['entry'] for s in selected)}")

    sections = {}

    for kind in args.kinds:
        section = analyse_kind(
            kind,
            selected,
            components,
            config,
            use_llm_judge,
            report_all=args.all_candidates,
            cross=args.cross,
        )

        if section is not None:
            sections[kind] = section

    if len(sections) == 0:
        print("None of the selected entries has documents of the requested kinds.")
        return 1

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "kinds": args.kinds,
        "entries": [s["entry"] for s in selected],
        "llm_judge": use_llm_judge,
        "all_candidates": args.all_candidates,
        "cross": args.cross,
        "query_model": query_model_name(config),
        "embedder": embedding_model_name(config),
        "thresholds": {
            "top_k": config["dedup_top_k"],
            "distance": config["dedup_distance_threshold"],
            "strong_distance": config["dedup_strong_distance_threshold"],
            "syntactic": config["dedup_syntactic_threshold"],
        },
        "sections": sections,
    }

    json_path, markdown_path = write_report(report, report_folder)

    print("")
    for kind, section in sections.items():
        aggregates = section["aggregates"]
        print(
            f"{aggregates['documents_with_near_exact_or_likely_duplicate']} of "
            f"{aggregates['documents']} analysed {kind} have a near-exact or likely duplicate "
            "elsewhere in the AFP."
        )
    print(f"Wrote report to {markdown_path} and {json_path}.")

    # The positive control is the only hard failure: if documents do not even retrieve themselves,
    # the numbers of this run are meaningless.
    for kind, section in sections.items():
        control = section["self_retrieval"]

        if control["failure_fraction"] > SELF_RETRIEVAL_FAILURE_LIMIT:
            print(
                f"Error: only {control['self_retrieved']} of {control['documents']} {kind} "
                "retrieved themselves. The corpus and the queries do not use the same embedding "
                "space, so the results of this run cannot be trusted."
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
