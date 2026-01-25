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

TMP_ARCHIVE = ".tmp_archive.tar.gz"


def download_and_extract(remote_url, target_path):
    if not os.path.exists(target_path):
        print(f"Downloading {remote_url} to file .tmp_archive.tar.gz...")
        urllib.request.urlretrieve(remote_url, TMP_ARCHIVE)

        if not tarfile.is_tarfile(TMP_ARCHIVE):
            os.remove(TMP_ARCHIVE)
            raise ValueError(
                f"Remote URL {remote_url} does not lead to a tar file. Only extracting tar files is supported."
            )

        try:
            file = tarfile.open(TMP_ARCHIVE)
            file.extractall()
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


def build_index(config):
    """
    1. Checks if the index (solr/local) already exists. If yes, stops.
    2. Backs up the existing 'find_facts' directory using tarfile if it has changed.
    3. Runs the Isabelle 'find_facts_index' command.
    """
    isabelle_bin = config["isabelle_binary_file"]
    afp_folder = str(Path(config["afp_folder"]).absolute())
    isabelle_version = config["isabelle_version"]

    # Path: ~/.isabelle/Isabelle2025-2
    isabelle_home = Path.home() / ".isabelle" / isabelle_version
    find_facts_dir = isabelle_home / "find_facts"
    solr_index_dir = find_facts_dir / "solr" / "local"

    # 1. Stop if index already exists and is not empty
    if solr_index_dir.exists() and any(solr_index_dir.iterdir()):
        print(
            f"Index already exists in {solr_index_dir} and is not empty. Skipping build."
        )
        return

    # 2. Backup existing find_facts directory (if it exists)
    if find_facts_dir.exists():
        backup_pattern = str(isabelle_home / "find_facts_backup_*.tar.gz")
        existing_backups = sorted(glob.glob(backup_pattern))

        should_backup = True

        # Check if the folder is actually newer than the last backup
        if existing_backups:
            last_backup = Path(existing_backups[-1])
            if find_facts_dir.stat().st_mtime < last_backup.stat().st_mtime:
                print(
                    f"Skipping backup: {find_facts_dir.name} has not changed since last backup."
                )
                should_backup = False

        if should_backup:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_file = isabelle_home / f"find_facts_backup_{timestamp}.tar.gz"
            print(f"Creating backup: {backup_file.name}...")

            # Use Python's built-in tarfile module
            with tarfile.open(backup_file, "w:gz") as tar:
                # arcname="find_facts" ensures the folder is at the root of the archive
                # avoiding full absolute paths inside the tar
                tar.add(find_facts_dir, arcname="find_facts")

    # 3. Build the index
    print("Building FindFacts index...")
    sessions = config.get(
        "isabelle_sessions", ["HOL", "Laws_of_Large_Numbers"]
    )  # Example sessions to test if indexing works

    cmd = [isabelle_bin, "find_facts_index", "-A", afp_folder, "-v"] + sessions

    try:
        subprocess.run(cmd, check=True)
        print("Indexing completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error building index: {e}")
