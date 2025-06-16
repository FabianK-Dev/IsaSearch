# Define the main files
MAIN_TEX = main.tex
BIB_FILE = bibliography.bib

# Define output PDFs
MAIN_PDF = main.pdf

# Define latexmk command
LATEXMK = latexmk

# Phony targets
.PHONY: all clean main

# Default target
all: clean main

# Build main version
main: $(MAIN_PDF)
	@$(MAKE) clean_aux

# Compile main version
$(MAIN_PDF): $(MAIN_TEX) $(BIB_FILE)
	$(LATEXMK) -pdf -bibtex $(MAIN_TEX)

# Clean only auxiliary files, keep the PDF
clean_aux:
	rm -f *.acn *.aux *.bbl *.blg *.fdb_latexmk *.fls *.glo *.lof *.log *.lot *.out *.toc *.xdy

# Clean up the generated files, including the PDF
clean: 
	$(LATEXMK) -C
	rm -f *.acn *.aux *.bbl *.blg *.fdb_latexmk *.fls *.glo *.lof *.log *.lot *.out *.toc *.xdy $(MAIN_PDF)
