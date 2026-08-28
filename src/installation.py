"""
installation.py: This file installs the components configured under config["components"], i.e.
Isabelle and the Archive of Formal Proofs, and builds the Isabelle FindFacts index from them.

A component is installed in one of two ways, chosen by its configuration:

- Archive (config["components"][name]["archive_url"] and ["version"]): a released distribution is
  downloaded and unpacked. This is how Isabelle is pinned to a release, because the Isabelle git
  mirror only carries the development branch and has no release branches or tags.
- Git (config["components"][name]["remote_url"] and ["target_branch"]): a shallow clone that is
  fetched and reset to the remote on every update. This is how the AFP is tracked, whose release
  mirrors are separate repositories with a single 'master' branch.

Both refuse to overwrite a checkout that was installed from a different source. Bumping the pinned
version is a deliberate edit of config.json, so an existing tree is reported and left alone rather
than silently deleted.
"""

import os
import shutil
import tarfile
import json
import subprocess
import glob
import requests
from pathlib import Path
from datetime import datetime


# Size of the chunks the component archive is streamed in. The Isabelle distribution is well over a
# gigabyte, so it is never held in memory as a whole.
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


# The file an unpacked Isabelle distribution identifies itself with, relative to its root. Its
# content is the release name, e.g. "Isabelle2025-2", which is what config["...]["version"] is
# compared against to decide whether the installed tree is already the pinned one.
VERSION_MARKER = os.path.join("etc", "ISABELLE_IDENTIFIER")


# Read the version an installed archive component identifies itself with, or None if the folder does
# not exist or carries no marker.
def installed_archive_version(local_path):
    marker = os.path.join(local_path, VERSION_MARKER)

    try:
        with open(marker, "r") as file:
            return file.read().strip()
    except OSError:
        return None


# Download and unpack a released distribution into comp_config["local_folder"].
def install_from_archive(name, comp_config):
    local_path = comp_config["local_folder"]
    archive_url = comp_config["archive_url"]
    version = comp_config["version"]

    installed = installed_archive_version(local_path)

    if installed == version:
        print(f"{name} {version} is already installed in '{local_path}'.")
        return

    if os.path.exists(local_path) and os.listdir(local_path):
        raise RuntimeError(
            f"'{local_path}' already contains an installation of {name} "
            f"({installed or 'of an unknown version'}), but {version} is configured. Remove the "
            f"folder to reinstall; it is not deleted automatically because it is several gigabytes."
        )

    print(f"Downloading {name} {version} from {archive_url}...")

    # The archive is unpacked next to its target and only then moved into place, so that an
    # interrupted download or extraction never leaves a half installed component behind. The
    # symlinks have to be resolved for that: in the container local_path is a symlink from the
    # image layer onto the state volume, and staging on the wrong side of it would both fill the
    # container layer and turn every move below into a multi gigabyte copy.
    resolved = os.path.realpath(local_path)
    parent = os.path.dirname(resolved)
    os.makedirs(parent, exist_ok=True)

    # The staging folder has a fixed name instead of a random one, so that a run that is killed
    # outright - which no cleanup handler survives - leaves at most one of them, and the next
    # attempt reclaims those several gigabytes instead of adding to them.
    staging = os.path.join(parent, "." + os.path.basename(resolved) + ".download")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)

    try:
        archive_path = os.path.join(staging, "component.tar.gz")

        with requests.get(archive_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            announced = response.headers.get("Content-Length")

            with open(archive_path, "wb") as file:
                file.writelines(response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE))

        # A connection that drops partway through a download of well over a gigabyte does not raise
        # here; it just ends the stream. Without this check the truncated file is handed to tarfile,
        # which reports an unexpected end of data and says nothing about the actual cause.
        downloaded = os.path.getsize(archive_path)

        if announced is not None and downloaded != int(announced):
            raise RuntimeError(
                f"The download of {name} from {archive_url} is incomplete: got {downloaded} of "
                f"{announced} bytes. Run this again to retry."
            )

        print(f"Extracting {name} into '{local_path}'...")
        extracted = os.path.join(staging, "extracted")

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(extracted, filter="data")

        # A distribution archive holds a single top level directory named after the release.
        entries = os.listdir(extracted)

        if len(entries) != 1:
            raise RuntimeError(
                f"Expected exactly one top level directory in the {name} archive, "
                f"found {len(entries)}: {sorted(entries)}"
            )

        root = os.path.join(extracted, entries[0])
        downloaded = installed_archive_version(root)

        # Checked before anything is moved, so that a wrong URL leaves no installation behind.
        if downloaded is not None and downloaded != version:
            raise RuntimeError(
                f"The archive at {archive_url} contains {downloaded}, but {version} is "
                f"configured. Fix config['components']['{name}']."
            )

        # The content is moved into local_path rather than local_path being replaced by the
        # extracted directory, because in the container local_path is a symlink onto the state
        # volume and replacing it would break that link. The directory holding the version marker
        # goes last, so that a run that is killed halfway through is recognised as incomplete
        # instead of being reported as already installed on the next start.
        marker_root = VERSION_MARKER.split(os.sep)[0]
        entries = sorted(os.listdir(root), key=lambda entry: entry == marker_root)

        # The resolved path, not local_path: os.makedirs(..., exist_ok=True) raises FileExistsError
        # on a symlink whose target does not exist yet, which is what local_path is in a container
        # whose state volume has not been populated.
        os.makedirs(resolved, exist_ok=True)

        for entry in entries:
            shutil.move(os.path.join(root, entry), os.path.join(resolved, entry))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"{name} {version} installed in '{local_path}'.")


# Run a git command, turning a missing git binary into an error that names the cause. check_and_update
# is the first thing a build run does, and a container without git would otherwise fail with a bare
# FileNotFoundError from deep inside subprocess.
def run_git(arguments, capture=False):
    try:
        return subprocess.run(
            ["git"] + arguments, check=True, capture_output=capture, text=True
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "The 'git' command is not available, but it is required to download and update the "
            "configured components."
        ) from error


# Update an existing shallow clone, or create one if it does not exist yet.
def install_from_git(name, comp_config):
    local_path = comp_config["local_folder"]
    remote_url = comp_config["remote_url"]
    target_branch = comp_config["target_branch"]

    if os.path.exists(local_path) and os.path.isdir(os.path.join(local_path, ".git")):
        # Pulling a release branch into a checkout of a different repository silently produces a
        # mixture of both, which only shows up much later as build errors. Re-pinning a component is
        # a config edit, so an existing checkout of another remote is reported instead.
        try:
            origin = run_git(
                ["-C", local_path, "remote", "get-url", "origin"], capture=True
            ).stdout.strip()
        except subprocess.CalledProcessError:
            origin = None

        if origin is not None and origin != remote_url:
            raise RuntimeError(
                f"'{local_path}' is a checkout of {origin}, but {name} is configured to track "
                f"{remote_url}. Remove the folder so it can be cloned again."
            )

        print(f"Updating {name} in {local_path}...")

        # Fetch and reset rather than pull. The checkout is ours and is never committed into, so
        # "update" means "make it match the remote" - and a merge cannot express that. The AFP
        # release mirrors are re-generated rather than appended to, so the remote history is
        # rewritten from time to time; against a shallow clone 'git pull' then reports divergent
        # branches and refuses to do anything until a merge strategy is configured. A reset always
        # works and cannot leave a half merged tree behind. Untracked files survive it, so a
        # submission placed under thys/ by hand is not lost - but a modified tracked file is, which
        # is why a working tree under review wants config["check_for_updates"] = false.
        try:
            run_git(
                ["-C", local_path, "fetch", "--depth", "1", "origin", target_branch]
            )
            run_git(["-C", local_path, "reset", "--hard", "FETCH_HEAD"])
        except subprocess.CalledProcessError as e:
            print(
                f"Warning: could not update {name}: {e}. Continuing with the checkout that is "
                f"already in '{local_path}'."
            )
    else:
        print(f"Cloning {name} into folder '{local_path}'...")
        try:
            run_git(
                ["clone", "--depth", "1", "-b", target_branch, remote_url, local_path]
            )
        except subprocess.CalledProcessError as e:
            print(f"Error cloning {name}: {e}")


def check_and_update(name, comp_config):
    if "archive_url" in comp_config:
        install_from_archive(name, comp_config)
    else:
        install_from_git(name, comp_config)


# Fetch the Isabelle contrib components, i.e. the tools that are not part of the source tree itself.
#
# Only a repository checkout needs this. A release distribution already ships its components under
# contrib/, and it does not ship Admin/ at all - but 'isabelle components -I' writes an
# init_components line into $ISABELLE_HOME_USER/etc/settings that points at
# $ISABELLE_HOME/Admin/components/main. Against a release that catalog does not exist, so every
# later 'isabelle' invocation aborts with "Bad component catalog file" until that settings file is
# removed by hand. Running this against an archive installation therefore does not merely do
# nothing, it breaks the installation.
def setup_isabelle_components(config):
    comp_config = config["components"]["isabelle"]
    isabelle_bin = os.path.join(comp_config["local_folder"], "bin", "isabelle")

    if not os.path.exists(isabelle_bin):
        raise FileNotFoundError(f"Isabelle binary not found at: {isabelle_bin}")

    if "archive_url" in comp_config:
        print(
            "Isabelle was installed from a release archive, which already contains its "
            "components. Skipping the component setup."
        )
        return

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
    # Not fatal on purpose: fetching the contrib components can fail for transient reasons while the
    # installation is still usable, and whatever actually depends on a missing component fails right
    # afterwards in the index build, which does stop the run.
    except subprocess.CalledProcessError as e:
        print(f"Warning: error setting up Isabelle components: {e}")


def isabelle_binary(config):
    return os.path.join(
        config["components"]["isabelle"]["local_folder"], "bin", "isabelle"
    )


# Read one setting out of the installed Isabelle, rather than assuming its value. Everything that
# depends on how the distribution is laid out or built comes from here, so that it stays right
# across releases instead of drifting until something breaks quietly.
def isabelle_getenv(config, name):
    isabelle_bin = isabelle_binary(config)

    if not os.path.exists(isabelle_bin):
        raise FileNotFoundError(f"Isabelle binary not found at: {isabelle_bin}")

    result = subprocess.run(
        [isabelle_bin, "getenv", "-b", name],
        capture_output=True,
        text=True,
        check=True,
    )
    value = result.stdout.strip()

    if not value:
        raise RuntimeError(f"Isabelle reported an empty {name}.")

    return value


# The same setting, for use inside an error message, where failing to read it must not replace the
# error being reported.
def isabelle_getenv_quiet(config, name):
    try:
        return isabelle_getenv(config, name)
    except Exception:
        return "unknown"


# Where Isabelle keeps the state of the installed distribution.
#
# It is not ~/.isabelle: Isabelle's own etc/settings sets
# ISABELLE_HOME_USER="$USER_HOME/.isabelle/$ISABELLE_IDENTIFIER" whenever ISABELLE_IDENTIFIER is
# set, which every release distribution does, so the real location carries the release name.
# Guessing it wrong is quiet and expensive: the FindFacts index is then looked for in an empty
# directory, reported as missing and rebuilt on every single run, and a Solr started against that
# directory serves nothing.
def isabelle_home_user(config):
    return Path(isabelle_getenv(config, "ISABELLE_HOME_USER"))


# Where 'isabelle find_facts_index' writes, i.e. $ISABELLE_HOME_USER/find_facts as defined by the
# settings of the Find_Facts component.
def find_facts_home(config):
    return isabelle_home_user(config) / "find_facts"


def get_isabelle_version(config):
    isabelle_bin = isabelle_binary(config)

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


# Number of FindFacts backups that are kept, overridable through config["find_facts_backup_keep"].
# A backup holds a full copy of the Solr index, which is several gigabytes once the whole AFP is
# indexed, and one is written on every rebuild. Without a limit they accumulate for as long as the
# server is updated, so only the most recent ones are kept.
DEFAULT_BACKUP_KEEP = 2


# Delete all but the newest config["find_facts_backup_keep"] backups.
# The file names carry a zero padded timestamp, thus sorting them by name orders them by age.
def prune_backups(isabelle_home, config):
    keep = config.get("find_facts_backup_keep", DEFAULT_BACKUP_KEEP)

    if keep is None or keep < 0:
        return

    backups = sorted(glob.glob(str(isabelle_home / "find_facts_backup_*.tar.gz")))
    outdated = backups[: max(len(backups) - keep, 0)]

    for path in outdated:
        print(f"Removing outdated backup: {Path(path).name}...")

        try:
            os.remove(path)
        # Housekeeping must never take an indexing run down, e.g. because a backup is on a read-only
        # mount or was removed by hand in the meantime.
        except OSError as error:
            print(f"Warning: could not remove {path}: {error}")


# Every AFP session, read from the checkout's thys/ROOTS, where by AFP convention each line names
# one entry whose session carries the same name.
def afp_sessions(afp_folder):
    roots_file = Path(afp_folder) / "thys" / "ROOTS"

    if not roots_file.exists():
        raise FileNotFoundError(f"ROOTS file not found at: {roots_file}")

    with open(roots_file, "r") as f:
        return [line.strip() for line in f if line.strip()]


# Every HOL session of the Isabelle distribution (HOL, HOL-Library, HOL-Analysis, ..., HOLCF),
# asked of Isabelle itself rather than parsed out of its ROOT files: the distribution defines many
# sessions per ROOT and the format is not the AFP's one-name-per-line. Non-HOL logics (Pure, FOL,
# ZF, CTT) are left out - the corpus is a search over HOL mathematics, and their statements would
# only blur it.
def hol_distribution_sessions(config):
    result = subprocess.run(
        [isabelle_binary(config), "sessions", "-a"],
        capture_output=True,
        text=True,
        check=True,
    )
    sessions = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    hol = [name for name in sessions if name == "HOL" or name.startswith("HOL")]

    if not hol:
        raise RuntimeError(
            "'isabelle sessions -a' reported no HOL sessions. The tool's output was: "
            + result.stdout[:500]
        )

    return hol


# Expand the aliases in config["isabelle_sessions"] into concrete session names:
# - "all-AFP" stands for every session of the AFP checkout.
# - "all" stands for everything, i.e. the AFP plus every HOL session of the Isabelle distribution.
#   The distribution is included on purpose: theorems people search for live in HOL-Analysis or
#   HOL-Library at least as often as in the Archive, and a corpus without them silently caps what
#   any search over it can find.
# Aliases mix with literal names, duplicates are dropped and the first occurrence keeps its place.
def expand_session_aliases(sessions, afp_folder, config):
    if isinstance(sessions, str):
        sessions = [sessions]

    expanded = []

    for name in sessions:
        if name == "all-AFP":
            expanded.extend(afp_sessions(afp_folder))
        elif name == "all":
            expanded.extend(afp_sessions(afp_folder))
            expanded.extend(hol_distribution_sessions(config))
        else:
            expanded.append(name)

    return list(dict.fromkeys(expanded))


# Drop the sessions named by config["isabelle_excluded_sessions"] from the session list.
#
# A single failing session makes the whole index build fail (see below), so one entry that is broken
# in the Archive itself blocks the corpus for everything else. Excluding it is the way out, and it
# is deliberately loud: an entry that is not indexed can never be searched or reported as a
# duplicate, so what a corpus is missing has to be visible in the build output rather than inferred
# from its absence.
#
# Note that this only stops a session from being requested, not from being built: a session that an
# included one depends on is still built as a dependency. Excluding a session that others build on
# therefore achieves nothing, and the build fails as before.
def without_excluded_sessions(sessions, config):
    excluded = set(config.get("isabelle_excluded_sessions", []))

    if not excluded:
        return sessions

    remaining = [session for session in sessions if session not in excluded]
    dropped = sorted(set(sessions) & excluded)

    if dropped:
        print(
            f"Excluding {len(dropped)} session(s) from the index, so they are not part of the "
            f"corpus: {', '.join(dropped)}."
        )

    # A name that matches nothing is almost always a typo, and a typo here is silent: the session it
    # was meant to exclude is built, fails, and takes the run down with it.
    unknown = sorted(excluded - set(sessions))

    if unknown:
        print(
            f"Warning: config['isabelle_excluded_sessions'] names {len(unknown)} session(s) that "
            f"are not in the session list anyway: {', '.join(unknown)}."
        )

    return remaining


def build_index(config):
    """
    1. Checks if index exists AND if the session list matches the last build.
    2. If sessions changed or index is missing:
       a. Backs up existing 'find_facts' (including old index).
       b. Deletes old index (to ensure clean build).
       c. Runs Isabelle 'find_facts_index'.
       d. Saves the new session list to 'indexed_sessions.json'.
    """
    isabelle_bin = isabelle_binary(config)
    afp_folder = str(Path(config["components"]["afp"]["local_folder"]).absolute())

    # Paths, asked of Isabelle rather than assumed: see isabelle_home_user above.
    find_facts_dir = find_facts_home(config)
    isabelle_home = find_facts_dir.parent
    solr_index_dir = find_facts_dir / "solr" / "local"
    state_file = find_facts_dir / "indexed_sessions.json"

    current_sessions = expand_session_aliases(
        config.get("isabelle_sessions", ["all"]), afp_folder, config
    )
    current_sessions = without_excluded_sessions(current_sessions, config)

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

            prune_backups(isabelle_home, config)

    # 4. Build the index
    print(f"Building FindFacts index in {solr_index_dir}...")
    print(f"Building FindFacts index for sessions: {current_sessions}...")
    cmd = [isabelle_bin, "find_facts_index", "-A", afp_folder, "-v"]

    # Sessions declare their own timeout in their ROOT, chosen for the machine the Archive is built
    # on. timeout_scale multiplies whatever a session declares, so a slower machine can be given
    # more room without touching any of them - unlike an absolute timeout, which a session option
    # would override.
    timeout_scale = config.get("isabelle_timeout_scale")

    if timeout_scale is not None:
        cmd += ["-o", f"timeout_scale={timeout_scale}"]

    cmd += current_sessions

    try:
        subprocess.run(cmd, check=True)
        print("Indexing completed successfully.")

        # 5. Save the state (list of sessions) after success
        # Make sure directory exists (it should after build)
        find_facts_dir.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(current_sessions, f, indent=4)

    # A failed index build must not be reported as success: every later step reads the index, and a
    # caller that only sees the exit status - 'python3 -m src.corpus --index-only', the standalone
    # indexing step of a deployment -
    # would otherwise go on to build a corpus from the previous, stale index.
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Building the FindFacts index failed: {e}. A common cause on a server is that Solr is "
            "still running and holding the index open; stop it and run this again."
        ) from e
