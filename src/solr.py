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


def cleanup_solr():
    """Runs when the Python script exits."""
    global solr_process
    if solr_process:
        print("\nStopping Solr Docker container...")
        # We send a SIGTERM to the Docker process.
        # Since we use --rm, Docker usually cleans up, but just to be safe:
        try:
            # Stop container (name 'local-solr' defined below)
            subprocess.run(
                ["docker", "stop", "local-solr"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(
                f"Error stopping Solr: {e}",
                "The container may need to be stopped manually.",
            )
        print("Solr stopped.")


# Register the cleanup function to run at program exit
atexit.register(cleanup_solr)


def start_local_solr(config):
    """Start Solr via Docker based on the user command."""
    global solr_process

    # The local path where Isabelle stores the FindFacts index, i.e. the same one that
    # src/installation.py builds into: ~/.isabelle/find_facts/solr/local
    user_home = os.path.expanduser("~")
    local_mount_path = os.path.join(
        user_home, ".isabelle", "find_facts", "solr", "local"
    )

    # Ensure the directory exists, otherwise Docker will complain
    os.makedirs(local_mount_path, exist_ok=True)

    # Build Docker command
    # --name local-solr: So we can easily find and stop it
    # --rm: Container is removed as soon as it stops
    cmd = [
        "docker",
        "run",
        "--rm",
        "-d",
        "-p",
        "8983:8983",
        "-v",
        f"{local_mount_path}:/opt/solr/server/solr/local",
        "solr:latest",
        "solr-precreate",
        "local",
        "/opt/solr/server/solr/local",
    ]

    print("Starting Solr Docker container...")
    try:
        # Start the Docker container
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
