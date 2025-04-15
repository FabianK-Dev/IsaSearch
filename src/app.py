import os
import re

AFP_FOLDER = "afp-2025-04-13"
AFP_ROOTS = AFP_FOLDER + "/thys/ROOTS"

entries = []

# Read the ROOTS file in $AFP/thys/ which contains a list of all entries in the AFP
if os.path.exists(AFP_ROOTS):
    with open(AFP_ROOTS) as entries_file:
        for line in entries_file:
            entries.append(line.rstrip())

def extract_theorems_regex(thy_path):
    if os.path.exists(thy_path):
        with open(thy_path, 'r') as thy_file:
            file_content = thy_file.read()

    # A simple RegEx for testing purposes that extracts and theorem code block from a .thy-file
    theorem_pattern = r'(theorem|lemma|corollary)\s+\w+(\s+:|:)\n(.+\n)*\n\n'
    theorems = []

    for match in re.finditer(theorem_pattern, file_content):
        match = match.group()
        match = match.strip()
        theorems.append(match)

    return theorems

def get_entry_files(entry):
    entry_folder = AFP_FOLDER + "/thys/" + entry
    found_thy_files = []
    found_tex_files = []

    if os.path.exists(entry_folder):
        for root, _, files in os.walk(entry_folder):
            for file in files:
                if file.endswith(".thy"):
                    found_thy_files.append({
                        "root": root,
                        "file": file,
                        "theorems": extract_theorems_regex(root + "/" + file)
                    })
                elif file.endswith(".tex"):
                    found_tex_files.append({
                        "root": root,
                        "file": file,
                    })

    return { "thy_files": found_thy_files, "tex_files": found_tex_files }

cyk = get_entry_files("CYK")
print(cyk)
