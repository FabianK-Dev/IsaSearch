"""
duplicate_scoring.py: The vocabulary and the scoring rules of the duplicate detection in
src/duplicates.py, i.e. everything that decides how similar two documents are and how strong the
evidence for a duplicate is.

Kept apart from the analysis itself because none of it does any I/O: no Solr, no ChromaDB, no LLM
and no report. Everything here is a pure function of the documents and the configured thresholds,
which is what makes the scoring rules readable and testable on their own.
"""

import difflib
import re

from src.documents import strip_proof
from src.llm import extract_marked_output


# Every AFP document ID contains the path of its theory file, so the entry a document belongs to is
# the first path segment after "/thys/". This is used both to select the documents of an entry and to
# exclude an entry from its own search results.
ENTRY_PATH_MARKER = "/thys/"

KIND_DEFINITIONS = "definitions"
KIND_THEOREMS = "theorems"
KINDS = [KIND_DEFINITIONS, KIND_THEOREMS]

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


# The thresholds that decide the tier of a candidate. Read in one place, so that the legend of the
# report cannot end up documenting other numbers than the ones the report was computed with.
def dedup_thresholds(config):
    return {
        "top_k": config["dedup_top_k"],
        "distance": config["dedup_distance_threshold"],
        "strong_distance": config["dedup_strong_distance_threshold"],
        "syntactic": config["dedup_syntactic_threshold"],
    }


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


# Similarity of two already normalized statements between 0.0 and 1.0. Kept apart from
# syntactic_similarity, so that a caller which compares one statement against many (see
# synthetic_ground_truth) can normalize every source once instead of once per pair.
def statement_similarity(a_statement, b_statement):
    # difflib reports a ratio of 1.0 for two empty strings, and a very high one for two statements
    # that are only a quote character. Both would be false duplicates.
    if (
        len(a_statement) < MIN_STATEMENT_LENGTH
        or len(b_statement) < MIN_STATEMENT_LENGTH
    ):
        return 0.0

    return difflib.SequenceMatcher(None, a_statement, b_statement).ratio()


# Similarity of two sources between 0.0 and 1.0, based on their normalized statements only.
# This is a purely syntactic signal that complements the semantic distance of the embeddings.
def syntactic_similarity(a_src, b_src):
    return statement_similarity(
        normalized_statement(a_src), normalized_statement(b_src)
    )


# All documents of the corpus that belong to the given entry, ordered by their ID for reproducibility.
# The IDs of the entry are selected before they are sorted, because sorting the whole corpus to pick
# out the few documents of one entry is the expensive part on the full AFP.
def entry_docs(index, entry):
    return [index[doc_id] for doc_id in sorted(entry_doc_ids(index, entry))]


# The IDs of those documents, for callers that only need to know how many there are.
def entry_doc_ids(index, entry):
    return [doc_id for doc_id in index if entry_of_id(doc_id) == entry]


# All entries that occur in the corpus.
def entries_in_index(index):
    entries = set()

    for doc_id in index:
        entry = entry_of_id(doc_id)

        if entry is not None:
            entries.add(entry)

    return entries


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
    text, _ = extract_marked_output(raw_output)
    text = text.strip()
    match = re.search(r"VERDICT\s*:\s*([A-Za-z]+)", text)

    if match is None:
        return UNKNOWN_VERDICT, text[:300]

    verdict = match.group(1).upper()

    if verdict not in VERDICTS:
        return UNKNOWN_VERDICT, text[:300]

    return verdict, text[match.end() :].strip()[:300]


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
#
# Only the duplicates of the documents in 'relevant_ids' are ever read back (see recall_at_k), so
# only pairs that involve one of them are compared. On the full AFP that is the difference between
# comparing a handful of entries and comparing the whole Archive against itself.
def synthetic_ground_truth(index, relevant_ids):
    by_name = {}

    for doc_id, doc in index.items():
        if entry_of_id(doc_id) is None:
            continue

        for name in defined_base_names(doc):
            by_name.setdefault(name, []).append(doc)

    duplicates = {}
    skipped_groups = 0
    # Normalizing a source runs a regex split over the whole document, and a document is compared
    # against every other member of every group it belongs to, thus each one is normalized once.
    statements = {}

    def statement_of(doc):
        if doc["id"] not in statements:
            statements[doc["id"]] = normalized_statement(doc["src"])

        return statements[doc["id"]]

    for docs in by_name.values():
        if len(docs) < 2:
            continue

        if len(docs) > GROUND_TRUTH_MAX_GROUP_SIZE:
            skipped_groups += 1
            continue

        if not any(doc["id"] in relevant_ids for doc in docs):
            continue

        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                a = docs[i]
                b = docs[j]

                if a["id"] not in relevant_ids and b["id"] not in relevant_ids:
                    continue

                if entry_of_id(a["id"]) == entry_of_id(b["id"]):
                    continue

                if (
                    statement_similarity(statement_of(a), statement_of(b))
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
        "thresholds": dedup_thresholds(config),
    }
