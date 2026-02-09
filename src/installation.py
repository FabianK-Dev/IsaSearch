"""
installation.py: This file automatically downloads a copy of the Archive of Formal Proofs from URL configured at config["afp_remote_url"] and extracts it into a folder name configured by config["afp_folder"], if it does not already exist.
"""

import os
import tarfile
import json
import subprocess
import glob
from pathlib import Path
from datetime import datetime


with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)


def check_and_update(name, comp_config):
    local_path = comp_config["local_folder"]
    remote_url = comp_config["remote_url"]
    target_branch = comp_config["target_branch"]

    if os.path.exists(local_path) and os.path.isdir(os.path.join(local_path, ".git")):
        print(f"Updating {name} in {local_path}...")
        try:
            subprocess.run(
                [
                    "git",
                    "-C",
                    local_path,
                    "pull",
                    "origin",
                    target_branch,
                    "--depth",
                    "1",
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error updating {name}: {e}")
    else:
        print(f"Cloning {name} into folder '{local_path}'...")
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "-b",
                    target_branch,
                    remote_url,
                    local_path,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Error cloning {name}: {e}")


# Install Isabelle components
def setup_isabelle_components():
    isabelle_bin = os.path.join(
        config["components"]["isabelle"]["local_folder"], "bin", "isabelle"
    )

    if not os.path.exists(isabelle_bin):
        raise FileNotFoundError(f"Isabelle binary not found at: {isabelle_bin}")

    print("Setting up Isabelle components...")
    try:
        subprocess.run([isabelle_bin, "components", "-I"], check=True)
        subprocess.run([isabelle_bin, "components", "-a"], check=True)
        subprocess.run(
            [isabelle_bin],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Isabelle components setup completed.")
    except subprocess.CalledProcessError as e:
        print(f"Error setting up Isabelle components: {e}")


def get_isabelle_version():
    isabelle_bin = os.path.join(
        config["components"]["isabelle"]["local_folder"], "bin", "isabelle"
    )

    if not os.path.exists(isabelle_bin):
        raise FileNotFoundError(f"Isabelle binary not found at: {isabelle_bin}")

    try:
        result = subprocess.run(
            [isabelle_bin, "version"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Return the first line of output as the version string
        version_line = result.stdout.strip().splitlines()[0]
        if version_line:
            return version_line

        raise ValueError("Could not find isabelle version in output.")

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
    isabelle_bin = os.path.join(
        config["components"]["isabelle"]["local_folder"], "bin", "isabelle"
    )
    afp_folder = str(Path(config["components"]["afp"]["local_folder"]).absolute())

    # Paths
    isabelle_home = Path.home() / ".isabelle"
    find_facts_dir = isabelle_home / "find_facts"
    solr_index_dir = find_facts_dir / "solr" / "local"
    state_file = find_facts_dir / "indexed_sessions.json"

    current_sessions = config.get("isabelle_sessions", ["all"])

    # Handle "all" sessions by reading from ROOTS file
    if current_sessions == "all" or current_sessions == ["all"]:
        roots_file = Path(afp_folder) / "thys" / "ROOTS"
        if roots_file.exists():
            with open(roots_file, "r") as f:
                current_sessions = [line.strip() for line in f if line.strip()]
        else:
            raise FileNotFoundError(f"ROOTS file not found at: {roots_file}")

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
