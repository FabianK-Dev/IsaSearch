"""
installation.py: This file automatically downloads a copy of the Archive of Formal Proofs from URL configured at config["afp_remote_url"] and extracts it into a folder name configured by config["afp_folder"], if it does not already exist.
"""

import os
import tarfile
import urllib.request
import json

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
