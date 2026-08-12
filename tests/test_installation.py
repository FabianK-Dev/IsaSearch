"""
test_installation.py: Offline tests for how the pinned components are installed.

Isabelle is pinned to a release by downloading its distribution archive, because the Isabelle git
mirror only carries the development branch; the AFP is pinned by tracking the release mirror of the
matching year. Both have to refuse to write into a checkout that came from somewhere else, since a
mixture of a release and a development tree only surfaces much later as build errors.

These tests need neither a network nor git. Run them with
'python3 -m unittest discover -s tests -t .' inside the root folder of the repository, or alone with
'python3 -m unittest tests.test_installation -v'.
"""

import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import unittest.mock

from src import installation

VERSION = "Isabelle2025-2"


# Build the bytes of a distribution archive: one top level directory named after the release, with
# the identifier file the installer recognises it by.
def archive_bytes(root=VERSION, identifier=VERSION):
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path, content in [
            (f"{root}/etc/ISABELLE_IDENTIFIER", f"{identifier}\n"),
            (f"{root}/bin/isabelle", "#!/bin/sh\n"),
        ]:
            payload = content.encode()
            info = tarfile.TarInfo(path)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))

    return buffer.getvalue()


# Stand-in for the streaming download in install_from_archive.
class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raised = False

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def raise_for_status(self):
        self.raised = True

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self.payload), chunk_size):
            yield self.payload[start : start + chunk_size]


class ArchiveInstallationTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

        self.local_path = os.path.join(self.folder, "Isabelle")
        self.comp_config = {
            "archive_url": "https://example.invalid/Isabelle2025-2_linux.tar.gz",
            "version": VERSION,
            "local_folder": self.local_path,
        }

    def install(self, payload=None):
        payload = archive_bytes() if payload is None else payload
        downloads = unittest.mock.Mock(return_value=FakeResponse(payload))

        with unittest.mock.patch.object(installation.requests, "get", downloads):
            installation.install_from_archive("isabelle", self.comp_config)

        return downloads

    def identifier(self):
        with open(os.path.join(self.local_path, "etc", "ISABELLE_IDENTIFIER")) as file:
            return file.read().strip()

    def test_the_release_is_unpacked_without_its_top_level_directory(self):
        self.install()

        self.assertEqual(self.identifier(), VERSION)
        self.assertTrue(
            os.path.exists(os.path.join(self.local_path, "bin", "isabelle"))
        )

    def test_an_already_installed_release_is_not_downloaded_again(self):
        self.install()
        downloads = self.install()

        downloads.assert_not_called()

    def write_installation(self, identifier):
        os.makedirs(os.path.join(self.local_path, "etc"))

        with open(
            os.path.join(self.local_path, "etc", "ISABELLE_IDENTIFIER"), "w"
        ) as file:
            file.write(identifier + "\n")

    def test_a_different_installed_version_is_reported_instead_of_replaced(self):
        self.write_installation("Isabelle2025-1")

        with self.assertRaises(RuntimeError) as raised:
            self.install()

        self.assertIn(self.local_path, str(raised.exception))
        self.assertIn("Isabelle2025-1", str(raised.exception))
        # The old installation is left in place, since it is several gigabytes on a real machine.
        self.assertEqual(self.identifier(), "Isabelle2025-1")

    def test_an_unrecognised_folder_is_reported_instead_of_overwritten(self):
        os.makedirs(self.local_path)

        with open(os.path.join(self.local_path, "important.txt"), "w") as file:
            file.write("not an Isabelle distribution")

        with self.assertRaises(RuntimeError) as raised:
            self.install()

        self.assertIn(self.local_path, str(raised.exception))

    def test_an_empty_folder_is_installed_into(self):
        # The container creates the state directories before the build runs, so the target of the
        # installation exists and is empty.
        os.makedirs(self.local_path)
        self.install()

        self.assertEqual(self.identifier(), VERSION)

    def test_an_archive_of_the_wrong_release_is_reported(self):
        with self.assertRaises(RuntimeError) as raised:
            self.install(
                archive_bytes(root="Isabelle2025-1", identifier="Isabelle2025-1")
            )

        self.assertIn(VERSION, str(raised.exception))
        # Nothing was installed, so a corrected URL can simply be retried.
        self.assertFalse(os.path.exists(self.local_path))

    def test_an_archive_without_a_single_root_is_reported(self):
        buffer = io.BytesIO()

        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for path in ["one/file", "two/file"]:
                info = tarfile.TarInfo(path)
                info.size = 0
                tar.addfile(info, io.BytesIO(b""))

        with self.assertRaises(RuntimeError):
            self.install(buffer.getvalue())

    def test_nothing_is_left_behind_when_the_download_fails(self):
        failing = unittest.mock.Mock(side_effect=OSError("network is down"))

        with (
            unittest.mock.patch.object(installation.requests, "get", failing),
            self.assertRaises(OSError),
        ):
            installation.install_from_archive("isabelle", self.comp_config)

        self.assertFalse(os.path.exists(self.local_path))
        self.assertEqual(os.listdir(self.folder), [])

    def test_a_leftover_staging_folder_is_reclaimed(self):
        # A process that is killed outright runs no cleanup, so the several gigabytes it staged have
        # to be reclaimed by the next attempt rather than accumulating on the volume.
        staging = os.path.join(self.folder, ".Isabelle.download")
        os.makedirs(staging)

        with open(os.path.join(staging, "component.tar.gz"), "w") as file:
            file.write("half a download")

        self.install()

        self.assertEqual(self.identifier(), VERSION)
        self.assertFalse(os.path.exists(staging))

    def test_the_installation_is_staged_next_to_the_resolved_target(self):
        # In the container local_folder is a symlink from the image layer onto the state volume.
        # Staging on the wrong side of it fills the container layer and turns every move into a
        # cross-device copy, which is exactly what the atomic rename is supposed to avoid.
        volume = os.path.join(self.folder, "volume")
        os.makedirs(volume)

        # Deliberately dangling: a fresh state volume does not contain the target yet.
        link = os.path.join(self.folder, "link-to-Isabelle")
        os.symlink(os.path.join(volume, "Isabelle"), link)
        self.comp_config["local_folder"] = link
        self.local_path = link

        staged_in = []
        real_makedirs = installation.os.makedirs

        def record(path, *arguments, **keywords):
            if os.path.basename(path).endswith(".download"):
                staged_in.append(os.path.dirname(path))

            return real_makedirs(path, *arguments, **keywords)

        with unittest.mock.patch.object(installation.os, "makedirs", record):
            self.install()

        # Compared as resolved paths, because the temporary folder itself sits behind a symlink on
        # macOS (/var -> /private/var).
        self.assertEqual(staged_in, [os.path.realpath(volume)])
        self.assertEqual(self.identifier(), VERSION)


class ComponentDispatchTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))

        self.local_path = os.path.join(self.folder, "afp")
        self.comp_config = {
            "remote_url": "https://github.com/isabelle-prover/mirror-afp-2025-2.git",
            "local_folder": self.local_path,
            "target_branch": "master",
        }

    def make_checkout(self):
        os.makedirs(os.path.join(self.local_path, ".git"))

    def test_a_component_with_an_archive_url_never_touches_git(self):
        git = unittest.mock.Mock()
        archive = unittest.mock.Mock()

        with (
            unittest.mock.patch.object(installation.subprocess, "run", git),
            unittest.mock.patch.object(installation, "install_from_archive", archive),
        ):
            installation.check_and_update(
                "isabelle",
                {
                    "archive_url": "https://example.invalid/x.tar.gz",
                    "version": VERSION,
                    "local_folder": self.local_path,
                },
            )

        archive.assert_called_once()
        git.assert_not_called()

    def test_a_checkout_of_another_remote_is_reported_instead_of_pulled(self):
        self.make_checkout()

        def run(arguments, **keywords):
            if "get-url" in arguments:
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    stdout="https://github.com/isabelle-prover/mirror-afp-devel.git\n",
                )

            raise AssertionError(f"git should not have been run: {arguments}")

        with (
            unittest.mock.patch.object(installation.subprocess, "run", run),
            self.assertRaises(RuntimeError) as raised,
        ):
            installation.check_and_update("afp", self.comp_config)

        self.assertIn("mirror-afp-devel", str(raised.exception))
        self.assertIn(self.local_path, str(raised.exception))

    def test_a_checkout_of_the_configured_remote_is_pulled(self):
        self.make_checkout()
        calls = []

        def run(arguments, **keywords):
            calls.append(arguments)

            if "get-url" in arguments:
                return subprocess.CompletedProcess(
                    arguments, 0, stdout=self.comp_config["remote_url"] + "\n"
                )

            return subprocess.CompletedProcess(arguments, 0)

        with unittest.mock.patch.object(installation.subprocess, "run", run):
            installation.check_and_update("afp", self.comp_config)

        self.assertIn("pull", calls[-1])

    def test_a_missing_git_is_reported_by_name(self):
        missing = unittest.mock.Mock(side_effect=FileNotFoundError("git"))

        with (
            unittest.mock.patch.object(installation.subprocess, "run", missing),
            self.assertRaises(RuntimeError) as raised,
        ):
            installation.check_and_update("afp", self.comp_config)

        self.assertIn("git", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
