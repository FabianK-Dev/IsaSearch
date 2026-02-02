"""
installation.py: This file automatically downloads a copy of the Archive of Formal Proofs from URL configured at config["afp_remote_url"] and extracts it into a folder name configured by config["afp_folder"], if it does not already exist.
"""

import os
import tarfile
import urllib.request
import json
import subprocess
import glob
from pathlib import Path
from datetime import datetime


with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

TMP_ARCHIVE = f".tmp_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"


def download_and_extract(remote_url, target_path):
    if not os.path.exists(target_path):
        print(f"Downloading {remote_url} to file {TMP_ARCHIVE}...")
        urllib.request.urlretrieve(remote_url, TMP_ARCHIVE)

        if not tarfile.is_tarfile(TMP_ARCHIVE):
            os.remove(TMP_ARCHIVE)
            raise ValueError(
                f"Remote URL {remote_url} does not lead to a tar file. Only extracting tar files is supported."
            )

        try:
            file = tarfile.open(TMP_ARCHIVE)
            file.extractall(path=target_path)
            file.close()
        except Exception as err:
            os.remove(TMP_ARCHIVE)
            raise Exception(f"Unexpected error occured: {err}")

        # Delete temporary archive after extracting
        os.remove(TMP_ARCHIVE)

        print("Verifying download...")

        if not os.path.exists(target_path):
            raise ValueError(
                f"Downloading from remote URL {remote_url} failed because target path {target_path} could not be found after installing. Something went wrong."
            )
    else:
        print(
            f"Skipping downloading because the target path {target_path} does already exist."
        )


def get_isabelle_version():
    isabelle_bin = os.path.join(config["isabelle_folder"], "bin", "isabelle")

    if not os.path.exists(isabelle_bin):
        raise FileNotFoundError(f"Isabelle binary not found at: {isabelle_bin}")

    try:
        result = subprocess.run(
            [isabelle_bin, "getenv", "ISABELLE_IDENTIFIER"],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("ISABELLE_IDENTIFIER="):
                # Return everything after the first "="
                return line.split("=", 1)[1]

        raise ValueError("Could not find ISABELLE_IDENTIFIER in output.")

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error executing Isabelle getenv: {e.stderr}")


def build_index(config):
    """
    1. Checks if index exists AND if the session list matches the last build.
    2. If sessions changed or index is missing:
       a. Backs up existing 'find_facts' (including old index).
       b. Deletes old index (to ensure clean build).
       c. Runs Isabelle 'find_facts_index'.
       d. Saves the new session list to 'indexed_sessions.json'.
    """
    isabelle_bin = os.path.join(config["isabelle_folder"], "bin", "isabelle")
    afp_folder = str(Path(config["afp_folder"]).absolute())
    isabelle_version = config["isabelle_version"]

    # Paths
    isabelle_home = Path.home() / ".isabelle" / isabelle_version
    find_facts_dir = isabelle_home / "find_facts"
    solr_index_dir = find_facts_dir / "solr" / "local"
    state_file = find_facts_dir / "indexed_sessions.json"

    # 0. Get current sessions from config
    current_sessions = config.get(
        "isabelle_sessions", ["HOL-ex", "Laws_of_Large_Numbers"]
    )

    # 1. Check logic: Index exists? Sessions changed?
    index_exists = solr_index_dir.exists() and any(solr_index_dir.iterdir())
    sessions_changed = True

    if state_file.exists():
        try:
            with open(state_file, "r") as f:
                previous_sessions = json.load(f)
            # Compare sorted lists to ignore order differences
            if sorted(previous_sessions) == sorted(current_sessions):
                sessions_changed = False
        except (json.JSONDecodeError, OSError):
            print("Warning: Could not read previous session state. Assuming changed.")

    # EXIT CONDITION: Index is there and nothing changed
    if index_exists and not sessions_changed:
        print(
            f"Index exists and session list unchanged ({len(current_sessions)} sessions). Skipping build."
        )
        return

    print(
        f"Build trigger: Index missing? {not index_exists} | Sessions changed? {sessions_changed}"
    )

    # 2. Backup existing find_facts directory
    if find_facts_dir.exists():
        backup_pattern = str(isabelle_home / "find_facts_backup_*.tar.gz")
        existing_backups = sorted(glob.glob(backup_pattern))
        should_backup = True

        if existing_backups:
            last_backup = Path(existing_backups[-1])
            # Skip if folder is older than last backup (unless sessions changed, then force backup!)
            if (
                not sessions_changed
                and find_facts_dir.stat().st_mtime < last_backup.stat().st_mtime
            ):
                print(
                    f"Skipping backup: {find_facts_dir.name} has not changed since last backup."
                )
                should_backup = False

        if should_backup:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_file = isabelle_home / f"find_facts_backup_{timestamp}.tar.gz"
            print(f"Creating backup: {backup_file.name}...")

            with tarfile.open(backup_file, "w:gz") as tar:
                tar.add(find_facts_dir, arcname="find_facts")

    # 4. Build the index
    print(f"Building FindFacts index for sessions: {current_sessions}...")
    cmd = [isabelle_bin, "find_facts_index", "-A", afp_folder, "-v"] + current_sessions

    try:
        subprocess.run(cmd, check=True)
        print("Indexing completed successfully.")

        # 5. Save the state (list of sessions) after success
        # Make sure directory exists (it should after build)
        find_facts_dir.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(current_sessions, f, indent=4)

    except subprocess.CalledProcessError as e:
        print(f"Error building index: {e}")
