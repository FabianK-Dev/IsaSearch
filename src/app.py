from pylatexenc.latex2text import LatexNodes2Text
from sentence_transformers import SentenceTransformer, CrossEncoder, util

import json
import os
import os.path
import re
import torch

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

    # A simple RegEx for testing purposes that extracts all theorem code block from a .thy-file
    theorem_pattern = r'(private)?\s+(theorem|lemma|corollary)(.+\n)*\n\n'
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

CACHE_FOLDER = ".cache"
ENTRY_DB_CACHE = f"{CACHE_FOLDER}/entry_db_cache.json"
entry_db = {}

if os.path.isfile(ENTRY_DB_CACHE):
    print("Cached entry_db_cache.json already exists. Loading...")

    with open(ENTRY_DB_CACHE, 'r') as file:
        data = file.read()

    entry_db = json.loads(data)

    print("Finished loading cached entry_db_cache.json")
else:
    print("Cached entry_db_cache.json does not already exist. Loading all entries...")

    for entry in entries:
        print(f"Loading entry: {entry}")
        entry_files = get_entry_files(entry)
        entry_db[entry] = entry_files

    # Double check in case that the .cache folder already exists, but the entry_db_cache.json does not exist
    if not os.path.exists(CACHE_FOLDER):
        os.makedirs(CACHE_FOLDER)

    with open(ENTRY_DB_CACHE, 'w') as file:
        json.dump(entry_db, file)

    print(f"Entries saved to {ENTRY_DB_CACHE}")

# Retrieve and Rerank pipeline
if not torch.cuda.is_available():
    print("No GPU found, so the CPU will be used instead which may increase encoding and search duration.")

bi_encoder = SentenceTransformer('multi-qa-MiniLM-L6-cos-v1')
bi_encoder.max_seq_length = 512
docs_to_retrieve = 100

cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')

# Create a list of documents to encode
# Each document consists of a theorem source code combined with the theorem's entry's parsed LaTeX document text
# As the theorem code is 1. unique and 2. more meaningful than the LaTeX document, it will be added first
print("Building documents list...")
documents = []

for entry in entry_db:
    print(f"Processing entry: {entry}")
    entry_document = ""

    for tex_file in entry_db[entry]["tex_files"]:
        if entry_document != "":
            entry_document = entry_document + "\n\n" + tex_file["plain_text"]
        else:
            entry_document = tex_file["plain_text"]
        
    for thy_file in entry_db[entry]["thy_files"]: 
        for theorem in thy_file["theorems"]:
            documents.append(theorem + "\n\n" + entry_document)

print(f"Built {len(documents)} documents.")
