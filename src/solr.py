"""
solr.py: This file connects to Solr and retrieves documents by their IDs.
"""

import sys
import time
import subprocess
import atexit
import os
import pysolr
import logging
from requests.exceptions import RequestException

# Global reference to the Solr Docker process
solr_process = None

# The name the container is started and stopped under. It has to be the same in both places, and it
# has to be passed to 'docker run': without it the container is anonymous, 'docker stop' finds
# nothing, and the container keeps running and keeps port 8983 - which then blocks the next start
# with "port is already allocated".
SOLR_CONTAINER_NAME = "local-solr"


# Check that Solr answers and that the core is loaded, by asking it for zero documents.
#
# Not '/admin/ping', which is what pysolr's ping() uses: the cores are created by Isabelle's
# Find_Facts, whose generated solrconfig.xml declares exactly one request handler, '/select'. There
# is no ping handler, so /admin/ping answers 404 on a core that is perfectly healthy. A search is
# also the better check of the two, because it is what every later query actually does.
def solr_is_healthy(solr):
    solr.search("*:*", rows=0)


def cleanup_solr():
    """Runs when the Python script exits."""
    global solr_process
    if solr_process:
        print(f"\nStopping the Solr container '{SOLR_CONTAINER_NAME}'...")
        # The container runs with --rm, so stopping it also removes it.
        try:
            stopped = subprocess.run(
                ["docker", "stop", SOLR_CONTAINER_NAME],
                check=False,
                capture_output=True,
                text=True,
            )
        except Exception as e:
            print(f"Error stopping Solr: {e}. Stop the container by hand.")
            return

        # Reported rather than assumed: claiming success while the container is in fact still up
        # leaves a process holding port 8983 that nobody is looking for.
        if stopped.returncode == 0:
            print("Solr stopped.")
        else:
            print(
                f"Warning: could not stop '{SOLR_CONTAINER_NAME}': "
                f"{stopped.stderr.strip()}. If it is still running it holds port 8983; remove it "
                f"with 'docker rm -f {SOLR_CONTAINER_NAME}'."
            )


# Register the cleanup function to run at program exit
atexit.register(cleanup_solr)


# The Solr image to serve the index with, overridable through config["solr_image"].
#
# Lucene reads its own format and older ones, never a newer one, so a Solr older than the one that
# wrote the index refuses to open the core and exits. The version that wrote it is the one Isabelle
# bundles, which Isabelle itself reports as SOLR_LUCENE_VERSION and stamps into every core it
# creates as luceneMatchVersion - so the image is derived from that rather than pinned to a number
# that silently rots at the next Isabelle release.
def solr_image(config):
    configured = config.get("solr_image")

    if configured:
        return configured

    from src.installation import isabelle_getenv

    return "solr:" + isabelle_getenv(config, "SOLR_LUCENE_VERSION")


# The same setting, for use inside an error message, where failing to read it must not replace the
# error being reported.
def isabelle_getenv_quiet(config, name):
    from src.installation import isabelle_getenv

    try:
        return isabelle_getenv(config, name)
    except Exception:
        return "unknown"


def start_local_solr(config):
    """Start Solr via Docker based on the user command."""
    global solr_process

    # Imported here rather than at the top of the file: this module is the low level Solr access
    # that src/installation.py sits above, and only this development convenience needs to reach up.
    from src.installation import find_facts_home

    # 'isabelle find_facts_index' writes a complete Solr home, with the index as a core named
    # 'local' inside it. Its location is asked of Isabelle, because it carries the release name and
    # guessing it wrong means serving an empty directory that never becomes ready. It has to exist:
    # there is nothing to serve before the corpus build has run.
    solr_home = str(find_facts_home(config) / "solr")

    if not os.path.isdir(os.path.join(solr_home, "local")):
        print(
            f"There is no FindFacts index at '{solr_home}'. Build it first with "
            "'python3 -m src.corpus --index-only'."
        )
        return False

    image = solr_image(config)
    print(f"Serving the FindFacts index at '{solr_home}' with {image}...")

    # Served directly out of that directory rather than precreated as a copy, so that a rebuilt
    # index is picked up by restarting the container.
    #
    # Deliberately without --rm: a Solr that cannot open the index exits within seconds, and --rm
    # would delete the container and its log along with it, leaving no way to find out why.
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        SOLR_CONTAINER_NAME,
        "-p",
        "8983:8983",
        "-v",
        f"{solr_home}:/var/solr/data",
        # As the user who owns the index, not as root. Solr refuses to start as root at all
        # ("Starting Solr as the root user is a security risk ... Exiting"), and running it that way
        # would leave root owned files inside the user's own ~/.isabelle, which the next
        # 'isabelle find_facts_index' then cannot write. Group 0 is what makes the image's /var/solr
        # writable for an arbitrary uid: it is owned by solr:0 with mode 0770.
        "--user",
        f"{os.getuid()}:0",
        image,
        "solr-foreground",
    ]

    print("Starting Solr Docker container...")
    try:
        # A container left behind by a run that was killed before its cleanup ran still holds both
        # the name and port 8983, so 'docker run' would fail on one or the other. Removing it first
        # is safe: it is ours, and it only ever serves an index that is rebuilt from the corpus.
        subprocess.run(
            ["docker", "rm", "-f", SOLR_CONTAINER_NAME],
            check=False,
            capture_output=True,
        )

        subprocess.run(cmd, check=True)
        # We mark that a process is running (for cleanup)
        solr_process = True

        print("Waiting for Solr to become ready (this may take a few seconds)...")
        # Wait until Solr really answers. Constructing pysolr.Solr does not contact the server, so
        # the readiness check has to issue a request; otherwise this loop reports success
        # immediately.
        for _ in range(30):
            try:
                solr_is_healthy(pysolr.Solr(config["solr_core_url"], timeout=1))
                print("\nSolr is up and running!")
                return True
            except Exception:
                time.sleep(1)
                sys.stdout.write(".")
                sys.stdout.flush()

        # The container is left in place on purpose, so that its log can still be read. A Solr that
        # cannot open the index - most often one older than the Lucene that wrote it - exits within
        # seconds and says why there and nowhere else.
        print(
            f"\nSolr did not become ready. It writes the reason to its log and nowhere else, so "
            f"read 'docker logs {SOLR_CONTAINER_NAME}' before changing anything. If the log names "
            f"an index version, set config['solr_image'] to match; Isabelle wrote this index with "
            f"Lucene {isabelle_getenv_quiet(config, 'SOLR_LUCENE_VERSION')}."
        )
        return False

    except FileNotFoundError:
        print("Error: 'docker' command not found. Please install Docker.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error starting Docker container: {e}")
        return False


def connect_solr(config):
    url = config["solr_core_url"]

    logging.getLogger("pysolr").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)

    try:
        print(f"Connecting to Solr at {url}...")
        solr = pysolr.Solr(url, always_commit=True, timeout=10)
        print("Querying Solr for health check...")

        solr_is_healthy(solr)
        return solr
    except (pysolr.SolrError, RequestException, Exception) as error:
        print(f"Could not connect to Solr at {url}.")

        # A deployed process (systemd, 'docker run' without -it, a cron job) has no terminal, so
        # asking a question there raises EOFError from inside this handler and buries the actual
        # cause in a confusing traceback. Report what is wrong instead and let the caller fail.
        if not sys.stdin.isatty():
            raise RuntimeError(
                f"Solr is not reachable at {url}. It has to be running and reachable before this "
                "process is started; see the deployment section of the README."
            ) from error

        # User input loop
        while True:
            choice = (
                input(
                    "Solr seems to be down. Do you want to start a local Solr instance via Docker? [Y/n]: "
                )
                .strip()
                .lower()
            )
            if choice in ["y", "yes", ""]:
                success = start_local_solr(config)
                time.sleep(10)
                if success:
                    return pysolr.Solr(url, always_commit=True, timeout=10)
                else:
                    print("Failed to start local Solr.")
                    sys.exit(1)
            elif choice in ["n", "no"]:
                print("Exiting because Solr is required.")
                sys.exit(1)
            else:
                print("Please answer with 'y' or 'n'.")


# Given a list of Solr document IDs, return a list of all documents identified by the IDs.
# Solr is queried in chunks, because a single request only returns 'chunk_size' documents at most.
def docs_by_ids(solr, ids, chunk_size=100):
    documents = []

    for i in range(0, len(ids), chunk_size):
        id_strings = []

        for _id in ids[i : i + chunk_size]:
            id_string = "id:" + _id
            id_strings.append(id_string)

        id_query = " OR ".join(id_strings)
        results = solr.search(id_query, start=0, rows=chunk_size)

        for result in results:
            documents.append(result)

    return documents


# Return the number of documents in Solr that match the given query, without retrieving them.
def count_docs(solr, query):
    results = solr.search(query, start=0, rows=0)

    return results.raw_response["response"]["numFound"]
