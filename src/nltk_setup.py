import nltk

def init_nltk_corpora():
    print("Downloading stopwords corpus and checking for updates...")
    nltk.download('stopwords')

    print("Downloading punkt_tab corpus for work tokenization and checking for updates...")
    nltk.download('punkt_tab')
