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

    # Build path: /home/user/.isabelle/{version}/find_facts/solr/local
    user_home = os.path.expanduser("~")
    isabelle_version = config.get("isabelle_version")

    if isabelle_version is None:
        print("Error: 'isabelle_version' is unknown.")
        return False

    # The local path where Isabelle stores the data
    local_mount_path = os.path.join(
        user_home, ".isabelle", isabelle_version, "find_facts", "solr", "local"
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
        # Wait until Solr really responds
        for i in range(30):
            try:
                # Simple ping on the admin endpoint or core
                solr = pysolr.Solr(config["solr_core_url"], timeout=1)
                solr.ping()
                print("Solr is up and running!")
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
    except (pysolr.SolrError, RequestException, Exception):
        print(f"Could not connect to Solr at {url}.")

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
                if success:
                    return pysolr.Solr(url, always_commit=True, timeout=10)
                else:
                    print("Failed to start local Solr.")
                    sys.exit(1)
            elif choice in ["n", "no"]:
                print("Exiting because Solr is required.")
                sys.exit(1)


# Given a list of Solr document IDs, return a list of all documents identified by the IDs.
def docs_by_ids(solr, ids):
    id_strings = []

    for _id in ids:
        id_string = "id:" + _id
        id_strings.append(id_string)

    id_query = " OR ".join(id_strings)
    results = solr.search(id_query, start=0, rows=100)

    return results
