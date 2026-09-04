"""
corpus.py: This file builds the corpus that everything else in this project reads. It is the one
process that writes, and it is meant to run alone.

What it produces, in this order:

1. The Isabelle installation and the AFP checkout, as pinned in config["components"].
2. The Isabelle FindFacts index, i.e. the Solr index of every command block of every configured
   session.
3. The document indexes, fetched from Solr: the theorems (config["solr_query"]) and the definitional
   commands (config["solr_query_definitions"]).
4. An informal description of every document, generated once by the configured LLM. This is the
   expensive part; it takes days for the whole AFP and is resumable, because descriptions are keyed
   by a checksum of the source code.
5. The ChromaDB collections, into which those descriptions are embedded. A rebuild also deletes what
   left the corpus and re-embeds what changed.

Afterwards the web application (src/app.py) and the duplicate detection (src/duplicates.py) attach
to the result strictly read-only, so any number of them may run at the same time and none of them
can ever start one of the steps above by accident.

The build comes in two phases, which is why '--index-only' exists. Step 2 runs
'isabelle find_facts_index', which writes the very Lucene index a running Solr holds open, so it has
to happen while Solr is stopped. Steps 3 to 5 read from Solr and therefore need it up. On a
deployment that means:

    python3 -m src.corpus --index-only    # with Solr stopped
    python3 -m src.corpus                 # with Solr running

Locally, where connect_solr can start a Solr container itself, a single 'python3 -m src.corpus' is
enough as long as no Solr is already serving the index.
"""

import argparse
import sys

from src.bootstrap import (
    DEFINITIONS_BUILD,
    boot_components,
    load_config,
    prepare_corpus_sources,
)
from src.documents import BUILD_CORPUS_COMMAND


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog=BUILD_CORPUS_COMMAND,
        description=(
            "Build the corpus that the web application and the duplicate detection read: the "
            "Isabelle and AFP checkouts, the FindFacts index, the document indexes, the LLM "
            "descriptions and the ChromaDB collections."
        ),
    )
    parser.add_argument(
        "--index-only",
        action="store_true",
        help=(
            "stop after installing the components and building the FindFacts index. This is the "
            "part of the build that requires Solr to be stopped, because the indexer writes the "
            f"same index a running Solr holds open. Run it first, then start Solr and run "
            f"'{BUILD_CORPUS_COMMAND}' for the rest."
        ),
    )

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config = load_config()

    # Done before boot_components, because the FindFacts index has to be built while Solr is down
    # and every later step needs Solr up. It also skips the LLM and embedding backend checks, which
    # a pure indexing run has no use for. A failure raises, so that the exit status of this step -
    # the only signal a deployment runbook has - never reports a stale index as a fresh one.
    if args.index_only:
        prepare_corpus_sources(config)
        print("Finished building the FindFacts index.")
        return 0

    boot_components(
        config,
        serve=False,
        # Both corpora, regardless of what the caller happens to be interested in: this is the build
        # step of a deployment and therefore has to produce everything that is later served.
        theorems=True,
        definitions=DEFINITIONS_BUILD,
        # The build owns no LLM output cache. It informalizes through the descriptions artifact and
        # never queries the query LLM, and the cache files belong to the processes that serve.
        llm_cache_name=None,
    )

    print("Finished building the corpora.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
