import os

AFP_FOLDER = "afp-2025-04-13"
AFP_ROOTS = AFP_FOLDER + "/thys/ROOTS"

entries = []

# Read the ROOTS file in $AFP/thys/ which contains a list of all entries in the AFP
if os.path.exists(AFP_ROOTS):
    with open(AFP_ROOTS) as entries_file:
        for line in entries_file:
            entries.append(line.rstrip())

def load_theorem(theorem_path):
    if os.path.exists(theorem_path):
        with open(theorem_path, 'r') as theorem_file:
            theorem_content = theorem_file.read()

    # TODO

def get_entry_files(entry):
    entry_folder = AFP_FOLDER + "/thys/" + entry
    found_files = []

    if os.path.exists(entry_folder):
        for root, _, files in os.walk(entry_folder):
            for file in files:
                if file.endswith(".thy") or file.endswith(".tex"):
                    found_files.append({
                        "root": root,
                        "file": file
                    })

    return found_files

print( get_entry_files("CYK") )
