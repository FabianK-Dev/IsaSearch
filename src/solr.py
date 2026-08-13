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
                f"{stopped.stderr.strip()}. Stop it by hand with "
                f"'docker rm -f {SOLR_CONTAINER_NAME}', it still holds port 8983."
            )


# Register the cleanup function to run at program exit
atexit.register(cleanup_solr)


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

    # Served directly out of that directory rather than precreated as a copy, so that a rebuilt
    # index is picked up by restarting the container.
    # --name local-solr: so we can easily find and stop it
    # --rm: container is removed as soon as it stops
    cmd = [
        "docker",
        "run",
        "--rm",
        "-d",
        "--name",
        SOLR_CONTAINER_NAME,
        "-p",
        "8983:8983",
        "-v",
        f"{solr_home}:/var/solr/data",
        "--user",
        "0:0",
        "solr:9.8.1",
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
        # Wait until Solr really responds. Constructing pysolr.Solr does not contact the server, so
        # the readiness check has to ping it; otherwise this loop reports success immediately.
        for _ in range(30):
            try:
                pysolr.Solr(config["solr_core_url"], timeout=1).ping()
                print("\nSolr is up and running!")
                return True
            except Exception:
                time.sleep(1)
                sys.stdout.write(".")
                sys.stdout.flush()

        print("\nSolr startup timed out.")
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
        print("Ping Solr for health check...")

        solr.ping()
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
