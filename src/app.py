from pylatexenc.latex2text import LatexNodes2Text

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
    theorem_pattern = r'theorem\s+\w+(\s+:|:)\n(.+\n)*\n\n'
    theorems = []

    for match in re.finditer(theorem_pattern, file_content):
        match = match.group()
        match = match.strip()
        theorems.append(match)

    return theorems

def parse_latex(tex_path):
    if os.path.exists(tex_path):
        with open(tex_path, 'r') as tex_path:
            file_content = tex_path.read()
    else:
        raise ValueError(f"Path {tex_path} does not exist.")
    
    # pylatexenc currently does not support parsing documents with the \href command
    # As a result, we have to replace it globally before parsing the document
    # See: https://github.com/phfaist/pylatexenc/issues/94
    # TODO: Potential fix: https://github.com/phfaist/pylatexenc/issues/94#issuecomment-1527266657
    #file_content = re.sub(r'\\href\b', r'\\texttt', file_content)
    file_content = "\\texttt".join(file_content.split("\\href"))
    plain_text = LatexNodes2Text().latex_to_text(file_content)

    # Replace two or more white spaces through single whitespace
    plain_text = re.compile(r"\s+").sub(" ", plain_text).strip()
    
    # Replace multiple newlines through single newlines
    plain_text = re.compile(r"\n+").sub("\n", plain_text)

    return plain_text

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
                        "plain_text": parse_latex(root + "/" + file)
                    })

    return { "thy_files": found_thy_files, "tex_files": found_tex_files }

for entry in entries:
    print(f"Entry: {entry}")
    entry_files = get_entry_files(entry)
    print(entry_files)
