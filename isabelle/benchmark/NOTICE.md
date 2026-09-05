# English stopwords provenance

`stopwords_english.txt` is the English file from NLTK's stopwords corpus,
retrieved on 2026-09-05 from:

https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/stopwords.zip

`STOPWORDS_README` is the unchanged upstream README. It credits PostgreSQL's
Snowball stopword lists and identifies the NLTK English additions. Keeping this
fixed copy avoids downloads and changes in the benchmark's noise vocabulary.

The NLTK package descriptor does not specify a license:
https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/stopwords.xml

Accordingly, this copy does not invent or substitute an NLTK software license for
the corpus. The upstream provenance notice is retained. Snowball's own software
license is available at https://github.com/snowballstem/snowball/blob/master/COPYING;
it is not evidence of a separate license grant for all NLTK corpus additions.
