from pylatexenc.latex2text import LatexNodes2Text
from sentence_transformers import SentenceTransformer, CrossEncoder, util
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from benchmark import benchmark

import json
import nltk
import os
import os.path
import re
import torch
import time
import pysolr

print("Loading config...")
with open("config.json", "r") as file:
    data = file.read()
    config = json.loads(data)

AFP_FOLDER = config["afp_folder"]
AFP_ROOTS = AFP_FOLDER + "/thys/ROOTS"

entries = []

# Required to remove stopwords
nltk.download('stopwords')

# Required for work tokenization
nltk.download('punkt_tab')

# Read the ROOTS file in $AFP/thys/ which contains a list of all entries in the AFP
if os.path.exists(AFP_ROOTS):
    with open(AFP_ROOTS) as entries_file:
        for line in entries_file:
            entries.append(line.rstrip())

# TODO: DEPRECATED => I will remove this method soon
def extract_theorems_regex(thy_path, entry):
    if os.path.exists(thy_path):
        with open(thy_path, 'r') as thy_file:
            file_content = thy_file.read()

    # A simple RegEx for testing purposes that extracts all theorem code block from a .thy-file
    theorem_pattern = r'(lemma|theorem|corollary)(.+\n)*\n'
    theorem_name_pattern = r'^(lemma|theorem|corollary)\s+(\S+)'
    theorems = []

    # Remove afp-XXXX-XX-XX/thys/ from path >= this is required for ID generation
    subpath = entry + "".join(thy_path.split(entry)[1:])

    for code_match in re.finditer(theorem_pattern, file_content):
        code_match = code_match.group()
        code_match = code_match.strip()
        
        if not (code_match.startswith("theorem ") or code_match.startswith("lemma ") or code_match.startswith("corollary ")):
            continue

        id_match = re.search(theorem_name_pattern, code_match)

        if id_match:
            theorem_type = id_match.group(1)
            theorem_name = id_match.group(2)
            theorem_id = subpath + "#" + theorem_type + "#" + theorem_name
        else:
            raise ValueError(f"Could not extract theorem type or theorem name in file {thy_path} in code block:\n{code_match}")

        theorem = {
            "id": theorem_id,
            "code": code_match
        }
        theorems.append(theorem)

    return theorems

def parse_latex(tex_path, stopwords_list):
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

    # Replace newlines through spaces
    plain_text = re.compile(r"\n").sub(" ", plain_text)

    # Replace two or more white spaces through single whitespace
    plain_text = re.compile(r"\s+").sub(" ", plain_text).strip()

    # Only allow letters or spaces in text
    plain_text = re.compile('[^a-zA-Z ]').sub("", plain_text) 

    # Remove words with three characters or less
    plain_text = re.compile(r'\b\w{1,3}\b').sub("", plain_text)

    # Remove stop words like e.g. "the", "a", "and", etc.
    plain_text_tokens = word_tokenize(plain_text)
    tokens_without_stopwords = [word for word in plain_text_tokens if not word in stopwords.words()]
    plain_text = (" ").join(tokens_without_stopwords)

    # print(plain_text)
    return plain_text

def get_entry_files(entry):
    entry_folder = AFP_FOLDER + "/thys/" + entry
    found_thy_files = []
    found_tex_files = []

    # stopwords will only be used once when parsing LaTeX documents which is why we
    # only define it in this scope. It will automatically be removed from RAM afterwards
    stopwords_list = stopwords.words() 

    if os.path.exists(entry_folder):
        for root, _, files in os.walk(entry_folder):
            for file in files:
                if file.endswith(".thy"):
                    found_thy_files.append({
                        "root": root,
                        "file": file,
                        "theorems": extract_theorems_regex(root + "/" + file, entry)
                    })
                elif file.endswith(".tex"):
                    found_tex_file = {
                        "root": root,
                        "file": file,
                        "plain_text": parse_latex(root + "/" + file, stopwords_list)
                    }

                    # root.tex is usually the most meaningful LaTeX document as it contains, the titel and abstract
                    # which is why it should appear first in the returned list
                    if file == "root.tex":
                        found_tex_files.insert(0, found_tex_file)
                    else:
                        found_tex_files.append(found_tex_file)

    return { "thy_files": found_thy_files, "tex_files": found_tex_files }

CACHE_FOLDER = ".cache"
ENTRY_DB_CACHE = f"{CACHE_FOLDER}/entry_db_cache.json"
entry_db = {}

solr = pysolr.Solr(config["solr_core_url"], always_commit=True, timeout=10)
solr.ping() # Health check

results = solr.search("command:theorem OR command:lemma OR command:corollary", start=0, rows=100)
print(results)

exit()

if os.path.isfile(ENTRY_DB_CACHE):
    print("Cached entry_db_cache.json already exists. Loading...")

    with open(ENTRY_DB_CACHE, 'r') as file:
        data = file.read()

    entry_db = json.loads(data)

    print(f"Finished loading {ENTRY_DB_CACHE}")
else:
    print(f"{ENTRY_DB_CACHE} does not already exist. Loading all entries...")

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

print("Building documents list...")
documents = []
document_ids = []
max_characters = 0
total_characters = 0

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
            document_str = theorem["code"] + "\n\n" + entry_document
            documents.append(document_str)
            document_ids.append(theorem["id"])
            
            num_characters = len(document_str)
            total_characters += num_characters

            if num_characters > max_characters:
                max_characters = num_characters

print(f"Built {len(documents)} documents.")
print(f"Maximum number of characters found in a document: {max_characters}")

avg_chars_per_doc = total_characters / len(documents)
avg_tokens_per_doc = avg_chars_per_doc / 4 # 1 token ~= 4 characters in English according to OpenAI (https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them)

print(f"Average number of characters per document: {avg_chars_per_doc}")
print(f"Average number of tokens per document: {avg_tokens_per_doc}")

# Retrieve and Rerank pipeline
if not torch.cuda.is_available():
    print("No GPU found, so the CPU will be used instead which may increase encoding and search duration.")

bi_encoder = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
bi_encoder.max_seq_length = 256*2
docs_to_retrieve = 1000

cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')

DOCS_CACHE = f"{CACHE_FOLDER}/embeddings_cache.pt"

if os.path.exists(DOCS_CACHE):
    encoded_embeddings = torch.load(DOCS_CACHE)
    print("Finished loading cached embeddings.")
else:
    encoded_embeddings = bi_encoder.encode(documents, convert_to_tensor=True, show_progress_bar=True)
    torch.save(encoded_embeddings, DOCS_CACHE)

def search(search_query):
    start = time.time()

    # Bi-encoder search
    question_encoded = bi_encoder.encode(search_query, convert_to_tensor=True)
    question_encoded = question_encoded.cuda()

    hits = util.semantic_search(question_encoded, encoded_embeddings, top_k=docs_to_retrieve)
    hits = hits[0] # It is in theory possible to search multiple queries at once, however we only provided one search query and thus 'hits' only contains one element

    # Cross-encoder search
    cross_encoder_input = [[search_query, documents[hit['corpus_id']]] for hit in hits] # corpus_id is the index of the original document in documents
    cross_encoder_scores = cross_encoder.predict(cross_encoder_input)

    hits = sorted(hits, key=lambda x: x['score'], reverse=True)
    results = []

    for hit in hits:
        results.append({
            "score": hit["score"],
            "document": documents[hit['corpus_id']],
            "id": document_ids[hit['corpus_id']]
        })

    end = time.time()
    search_duration  = end - start
    print(f"Search time: {end - start} sec")

    return {
        "results": results,
        "duration": search_duration
    }

#print( search("The continuum hypothesis can neither be proved nor refuted in ZFC") )
results = search("corollary ctm_ZFC_imp_ctm_not_CH")
print( benchmark.top_k_accuracy(results, "Independence_CH/Not_CH.thy#corollary#ctm_ZFC_imp_ctm_not_CH:") )
print( benchmark.discounted_cumulative_gain(results, "Independence_CH/Not_CH.thy#corollary#ctm_ZFC_imp_ctm_not_CH:") )

# for r in search("Commutative Group")["results"][:10]:
#     print(r["document"][:100] + "\n")
