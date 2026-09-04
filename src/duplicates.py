"""
duplicates.py: This file finds material of an AFP entry that already exists elsewhere in the Archive
of Formal Proofs. It was written for the experiment proposed by an AFP maintainer: take the n newest
AFP entries, search for their definitions in the AFP and ignore the definitions of the entry itself.

The analysis is strictly read-only and works entirely on the corpora that were built beforehand by
'python3 -m src.corpus', so it can run while the web application is up. An entry can only be
analysed once it is part of the corpus; for a submission that is not in the AFP checkout yet, see
the README. For every document of an analysed entry the following steps are performed:

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
import glob
import sys
import time
import tomllib

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from src.bootstrap import (
    load_config,
    boot_components,
    DEFINITIONS_LOAD,
)
from src.documents import (
    llm_concurrency,
    statement_excerpt,
    BUILD_CORPUS_COMMAND,
    KIND_DEFINITIONS,
    KIND_THEOREMS,
    KINDS,
)
from src.duplicate_report import (
    analyses_to_report,
    reported_documents,
    write_report,
)
from src.duplicate_scoring import (
    add_syntactic_similarity,
    aggregate,
    classify_analyses,
    dedup_thresholds,
    entries_in_index,
    entry_doc_ids,
    entry_docs,
    entry_of_id,
    parse_verdict,
    recall_at_k,
    self_retrieval_summary,
    synthetic_ground_truth,
    SELF_RETRIEVAL_FAILURE_LIMIT,
)
from src.embeddings import (
    document_embedding_string,
    add_doc_urls,
    embedding_model_name,
)
from src.llm import (
    cached_output,
    query_model_name,
    save_llm_output_cache,
    store_output,
)
from src.solr import docs_by_ids


# The LLM output cache of the duplicate detection, overridable through config["dedup_llm_cache"].
# It is deliberately not the cache of the web application: both rewrite their cache as a whole, so
# one shared file would lose everything the other one cached since it started. The two never share
# an entry anyway, because the judge prompt differs from every prompt the application uses.
DEDUP_LLM_CACHE = "llm_output_cache_dedup.json"


def dedup_llm_cache_name(config):
    return config.get("dedup_llm_cache", DEDUP_LLM_CACHE)


# Upper bound for the number of ChromaDB results that are requested per document and for the number
# of values of a single ChromaDB response, so that the response size stays bounded for large entries.
MAX_EXTRA_RESULTS = 300
MAX_RESPONSE_VALUES = 10000


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


# Scan the results one target returned for one document and pick the usable candidates out of them.
# Returns the candidates, the position and the distance at which the document retrieved itself
# (None if it did not show up at all), how many results the target returned and how many of them
# were skipped because they are no longer part of the corpus.
def scan_target_results(metadatas, distances, doc, kind, exclude_entry, corpus_index):
    hits = []
    self_position = None
    self_distance = None
    returned = 0
    stale = 0

    for position, (metadata, distance) in enumerate(zip(metadatas, distances), start=1):
        returned += 1
        candidate_id = metadata["source"]

        # The document itself is the positive control and never a candidate.
        if candidate_id == doc["id"]:
            self_position = position
            self_distance = distance
            continue

        if exclude_entry is not None and entry_of_id(candidate_id) == exclude_entry:
            continue

        # A collection is only ever added to, so it can still contain documents of an older version
        # of the corpus. Those cannot be reported, because neither their source code nor their
        # metadata is available anymore.
        if candidate_id not in corpus_index:
            stale += 1
            continue

        hits.append({"id": candidate_id, "distance": distance, "kind": kind})

    return hits, self_position, self_distance, returned, stale


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
def find_candidates(
    targets, prompts, query_docs, exclude_entry, home_kind, config, embedder=None
):
    top_k = config["dedup_top_k"]
    sizes = {}
    n_results = {}

    for kind, collection, corpus_index in targets:
        sizes[kind] = collection.count()

        if sizes[kind] == 0:
            raise RuntimeError(
                f"The ChromaDB collection for {kind} is empty. Build the corpus first "
                f"({BUILD_CORPUS_COMMAND})."
            )

        # Every document of the analysed entry may rank above the first candidate of another entry,
        # so enough results have to be requested to still have 'top_k' candidates left after the
        # exclusion. How many that is depends on how many documents the entry has in *this* corpus,
        # which is not the number of query documents: when a definition is matched against the
        # theorems corpus, the theorems of the same entry are excluded as well and there are usually
        # far more of them. The number of requested results is capped, so that the size of a single
        # response stays bounded.
        entry_size = len(entry_doc_ids(corpus_index, exclude_entry))
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

        # With several targets every collection would embed the identical texts again, which
        # doubles the requests to a remote embedding server. Embedding once through the shared
        # embedder of the corpus (see boot_components) yields exactly the vectors each
        # collection.query would have computed itself - same embedder instance, including the
        # truncation it applies - so the positive control still verifies the full query path.
        query_embeddings = None

        if len(targets) > 1 and embedder is not None:
            query_embeddings = embedder(query_texts)

        responses = {
            kind: collection.query(
                query_embeddings=query_embeddings, n_results=n_results[kind]
            )
            if query_embeddings is not None
            else collection.query(query_texts=query_texts, n_results=n_results[kind])
            for kind, collection, _ in targets
        }

        for j, doc in enumerate(batch):
            self_rank = None
            self_distance = None
            hits = []

            for kind, _, corpus_index in targets:
                response = responses[kind]
                (
                    target_hits,
                    self_position,
                    target_self_distance,
                    returned,
                    target_stale,
                ) = scan_target_results(
                    response["metadatas"][j],
                    response["distances"][j],
                    doc,
                    kind,
                    exclude_entry,
                    corpus_index,
                )

                hits.extend(target_hits)
                stale += target_stale

                # Only the home target's own ranking counts as the positive control, see above.
                if kind == home_kind and self_position is not None:
                    self_rank = self_position
                    self_distance = target_self_distance

                # If this corpus returned everything that was asked of it and still did not yield
                # 'top_k' usable candidates, the requested window was too small and duplicates that
                # rank below the documents of the entry itself were not seen. If the window covers
                # the whole collection there is nothing below it, so nothing was missed.
                if (
                    len(target_hits) < top_k
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

    # Every document is judged against several candidates and a popular candidate against several
    # documents, so the excerpts are cut once per document instead of once per pair. Cutting means
    # a regex split over the full source including its proof, which is by far the longest part.
    excerpts = {}

    def excerpt_of(doc):
        if doc["id"] not in excerpts:
            excerpts[doc["id"]] = statement_excerpt(doc["src"], max_length)

        return excerpts[doc["id"]]

    pair_prompts = [
        prompts["duplicate_judge"].format(
            item_a=excerpt_of(analysis["doc"]),
            item_b=excerpt_of(corpus_index[candidate["id"]]),
        )
        for analysis, candidate in pending
    ]

    # The prompts that actually need a completion, deduplicated in first-seen order: the same pair
    # can show up under several analysed documents, and generating it twice would waste a request
    # on an answer that the cache already holds by the time the second one is assigned.
    uncached = list(
        dict.fromkeys(
            prompt
            for prompt in pair_prompts
            if cached_output(cache, model_key, prompt) is None
        )
    )

    workers = llm_concurrency(config)

    if len(uncached) > 0:
        print(
            f"{len(uncached)} of the pairs are not cached yet, judging them with "
            f"{workers} request(s) in flight..."
        )

    def timed_generate(prompt):
        start = time.time()
        return model.generate(prompt), time.time() - start

    unsaved = 0

    # The requests are independent and the server processes several at once, so they are sent
    # concurrently, exactly like the informalization in src/documents.py. Only this thread ever
    # touches the cache: the workers do nothing but the HTTP request, and executor.map yields in
    # input order, so the cache contents are identical to what a sequential run produces.
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for prompt, (raw_output, duration) in tqdm(
                zip(uncached, executor.map(timed_generate, uncached)),
                total=len(uncached),
            ):
                store_output(cache, model_key, prompt, raw_output, duration)
                unsaved += 1

                # Writing the whole cache after every single judgement would dominate the runtime,
                # so it is written in batches instead.
                if config["enable_llm_output_cache"] and unsaved >= save_every:
                    save_llm_output_cache(cache, config, dedup_llm_cache_name(config))
                    unsaved = 0
    finally:
        # Whatever came back is saved even when a request failed or the run was interrupted, so
        # that the completions a long run already paid for are not judged again by the next one.
        if config["enable_llm_output_cache"] and unsaved > 0:
            save_llm_output_cache(cache, config, dedup_llm_cache_name(config))

    for (analysis, candidate), prompt in zip(pending, pair_prompts):
        verdict, justification = parse_verdict(
            cached_output(cache, model_key, prompt)["output"]
        )
        candidate["verdict"] = verdict
        candidate["justification"] = justification


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
def analyse_entry(
    entry, home_index, lookup_index, targets, home_kind, prompts, config, embedder
):
    query_docs = entry_docs(home_index, entry)

    if len(query_docs) == 0:
        print(f"Warning: entry {entry} has no documents in this corpus, thus skipping.")
        return None

    print(f"Analysing {len(query_docs)} documents of entry {entry}...")
    analyses = find_candidates(
        targets, prompts, query_docs, entry, home_kind, config, embedder
    )
    add_syntactic_similarity(analyses, lookup_index)

    return analyses


# Return the (collection, index) pair that holds the documents of one kind.
def corpus_target(kind, components):
    corpus = components["corpora"][kind]

    return corpus["collection"], corpus["document_index"]


# The document index of one kind.
def corpus_index(kind, components):
    return components["corpora"][kind]["document_index"]


# Run the analysis for one kind of document (definitions or theorems) over all selected entries.
# The query documents are always of the given kind. With 'cross' enabled they are matched against
# both corpora, so a definition can also find a theorem that states the same thing and vice versa.
def analyse_kind(
    kind, selected, components, config, use_llm_judge, report_all=False, cross=False
):
    collection, home_index = corpus_target(kind, components)
    targets = [(kind, collection, home_index)]

    if cross:
        other_kind = KIND_THEOREMS if kind == KIND_DEFINITIONS else KIND_DEFINITIONS
        targets.append((other_kind, *corpus_target(other_kind, components)))

    # Candidates can come from any target, so they are resolved against all of them. Merging the
    # indexes is safe because config["solr_query"] and config["solr_query_definitions"] select
    # disjoint Isabelle commands, so no document can be part of both corpora. Without a second
    # target there is nothing to merge, and copying the index would cost a full dictionary rebuild
    # of the whole corpus for a value that is only ever read.
    lookup_index = home_index

    if len(targets) > 1:
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
            kind,
            components["prompts"],
            config,
            components.get("embedder"),
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
    ground_truth, skipped_groups = synthetic_ground_truth(
        home_index, {analysis["doc"]["id"] for analysis in all_analyses}
    )

    # Collect every document that shows up in the report, so its links are resolved in one go.
    reported_ids = set()

    for analysis, candidates in reported_documents(all_analyses, report_all):
        reported_ids.add(analysis["doc"]["id"])
        reported_ids.update(candidate["id"] for candidate in candidates)

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

    return args


def main(argv=None):
    args = parse_args(argv)
    config = load_config()

    # Cross-kind matching queries the other corpus as well, so both are needed for it. Loading a
    # corpus that is never queried would cost gigabytes of memory on the full AFP, thus each one is
    # only loaded when this run actually reaches it.
    needs_definitions = KIND_DEFINITIONS in args.kinds or args.cross
    needs_theorems = KIND_THEOREMS in args.kinds or args.cross

    components = boot_components(
        config,
        # An analysis never builds anything: the corpus is built beforehand by src/corpus.py. That
        # is what lets it run next to the web application, which reads the same artifacts.
        serve=True,
        theorems=needs_theorems,
        definitions=DEFINITIONS_LOAD if needs_definitions else None,
        # The web application rewrites its own cache as a whole, so sharing one file with it would
        # make whichever process saves last drop the other's entries.
        llm_cache_name=dedup_llm_cache_name(config),
    )

    if needs_definitions and KIND_DEFINITIONS not in components["corpora"]:
        print(
            "The definitions corpus is not available. Build it with "
            f"'{BUILD_CORPUS_COMMAND}' first."
        )
        return 1

    use_llm_judge = config["dedup_llm_judge"] and not args.no_llm_judge
    report_folder = (
        args.report_dir
        if args.report_dir is not None
        else config["dedup_report_folder"]
    )

    # An entry is analysable if it has documents in *any* of the requested corpora, not only in the
    # first one. With '--kinds all' an entry that proves things about existing definitions has
    # theorems but no definitions of its own, and selecting on the definitions corpus alone would
    # report it as "not part of the corpus" and analyse nothing. analyse_entry already skips an
    # entry for the kinds it has no documents in, so the union is safe.
    available_entries = set()

    for kind in args.kinds:
        available_entries |= entries_in_index(corpus_index(kind, components))

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
        "thresholds": dedup_thresholds(config),
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
