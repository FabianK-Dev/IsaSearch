"""
helpers.py: Fixtures that more than one test module needs.

These are plain functions rather than a base class, because the test cases that need them already
inherit from unittest.TestCase and build quite different configurations on top. Every one of them
registers its own cleanup on the given test case, so a test only has to call it.
"""

import os
import shutil
import tempfile


# A temporary folder that is removed when the test finishes, whether it passed or not.
# 'ignore_errors' because a test that already failed must not fail a second time in its cleanup.
def temporary_folder(test_case):
    folder = tempfile.mkdtemp()
    test_case.addCleanup(shutil.rmtree, folder, True)

    return folder


# An installation that looks enough like Isabelle for the code that only checks whether the binary
# is there and then runs it through a patched subprocess. Returns the path of the fake binary.
def isabelle_stub(folder):
    isabelle_bin = os.path.join(folder, "bin", "isabelle")
    os.makedirs(os.path.dirname(isabelle_bin), exist_ok=True)

    with open(isabelle_bin, "w") as file:
        file.write("#!/bin/sh\n")

    return isabelle_bin
