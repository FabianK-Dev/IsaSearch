# KI-gestützte Theoremsuche in Isabelle: Ein transformerbasierter Ansatz

# Einleitung

## Motivation & Problemstellung
- Isabelle: generischer interaktiver Theorembeweiser mit besonderem Schwerpunkt auf Higher-Order Logic
- formale Verifizierung von Hard- und Software
- AFP: peer-reviewte Datenbank von Beweisbibliotheken
- stetig wachsende Zahl an Einträgen und formalen Theoremen im AFP (Quelle: Mining the Archive of Formal Proofs", https://www.isa-afp.org/statistics/ *(darf ich das zitieren?)*)
- Wiederverwendung bestehender Theorem essenziell um Duplikate zu vermeiden => zu wenig (Quelle: Mining the Archive of Formal Proofs" > Conclusion)
- Suchmaschinen wie isa-afp.org oder FindFacts oder Befehle wie find_theorems oder grep erlauben nur lexikalische Suche => keine Semantische Suche
- Keine Treffer bei abweichenden Begriffen oder Reihenfolge der Begriffe
- Keine Ähnlichkeitserkennung oder intelligentes Ranking der Suchergebnisse
- Schwierig für Nutzer bestehende Theoreme wieder zu finden
- gleichzeitig aber: Potential aktueller KI-Modelle für semantisches Retrieval

## Zielsetzung
- Ziel: Entwicklung und Evaluation einer KI-gestützten semantischen Suche nach Theoremen, Lemmas und Corollaries im AFP
- Verwendung vortrainierter Transformer-Modelle in Form von LLM zur Textgenerierung von Theorem-Beschreibungen und Optimieren einer Suchanfrage, Bi-Encoder zur Ähnlichkeitssuche und ChromaDB zur effizienten Speicherung und Vektorsuche
- Vergleich verschiedener Suchstrategien wie LLM-Umschreibung von Suchanfragen oder Metadatenintegration, anschließende Evaluation und Analyse durch Benchmark
- *(optional: Entwicklung der restAPI und Webseite, Docker-Container...?)*

## Forschungsfragen
- Wie effektiv sind LLMs bei der Umschreibung von formalen Theoremen, um deren Auffindbarkeit durch Suchanfragen des Nutzers zu verbessern?
- Wie wirkt sich das Optimieren einer Suchanfrage durch LLMs oder das Einbetten von Metadaten eines entsprechenden Theorems, wie Titel oder Abstract des Entries, auf die Suchqualtität aus?
- Wie effektiv ist die Theoremsuche laut des Benchmarks und wie robust ist sie gegenüber simulierten Fehlern bei Suchanfragen?

## *(optional: Aufbau?)*


# Hintergrund

## Isabelle, AFP und formale Beweise *(passt der Titel?)* *(soll ich mich wiederholen?)*
- Isabelle
- AFP: besteht aus Entries, die aus formalen Theoremen, Definitionen, Beweisen, etc. bestehen
- außerdem: Paper mit Title, Abstract

## Bestehende Suchmechanismen *(soll ich mich wiederholen?)*
- FindFacts, isa-afp.org, find_theorem, grep?
- Was ist FindFacts? Wie funktioniert die bisherige Suche?
- aber: unterstützen jeweils nur lexikalische Suche, keine Semantische Suche

## Transformerbasierte Sprachmodelle
- soll ich Transformer "from scratch" erklären oder ist das zu viel?

## ChromaDB *(passt der Titel?)*
- soll ich ChromaDB erklären oder nur kurz erwähnen/erklären?
- z.B. "https://aclanthology.org/2024.findings-emnlp.470.pdf" geht nur kurz darauf ein
- soll ich dieses Unterkapitel mit "Transformerbasierte Sprachmodelle" mergen (statt extra einem Unterkapitel nur für ChromaDB?)

## Verwandte Arbeiten
- Gao, G., Ju, H., Jiang, J., Qin, Z., & Dong, B. (2024). A semantic search engine for Mathlib4. arXiv preprint arXiv:2403.13310.
- Huch, F., & Krauss, A. (2022). FindFacts: a scalable theorem search. arXiv preprint arXiv:2204.14191.
- genügen 2 Verwandte Arbeiten?


# Methodik

## Programmaufbau
- Detaillierte Schritt-für-Schritt Erklärung des Programm-Ablaufs, z.B.:
- benötigt fertigen FindFacts-Index, d.h. baut darauf auf
- verbindet sich mit bereits laufender Solr-Datenbank
- lädt aus der Solr-DB nur Dokumente mit dem "command" theorem/lemma/corollary
- prüft für jedes Theorem, ob dieses bereits vom in der config festgelegten LLM beschrieben informalisiert wurde 
- ...
- startet Flask-API-Server zur Bereitstellung einer REST-API

## Informalisierung der Theoreme
- was ist "Informalisierung" der Theorem?
  - => LLM umschreibt den Theorem-Code in informale Sprache, damit es leichter zum Finden ist
- warum ausgerechnet das LLM microsoft/Phi-3.5-mini-instruct?
  - => technische Limitationen
  - => Wahl anhand von LLM Leaderboard
- Beispiel: Prompt, Input Theorem, Umschreibung *(Frage: Prompt-Beispiel lieber hier oder in den Anhang mit Referenz?)*


# Benchmark

## Aufbau des Benchmarks
- Quelle: Freek's "Top 100 Theorems in Isabelle"
- Struktur der Benchmark-Tabelle: ID, Title, Theorem, Target Identifiers, Link, Session, Annotation als CSV *(soll ich jede column erklären?)*
- Generierung der Queries: Title, Natural language query, noisy natural language query
- Beispiel

## Verwendete Metriken
- jede Metrik als Formel erklären => was sagt diese Metrik aus?


# Ergebnis und Analyse

## Vergleich der Suchstrategien
- alle 5 Suchstrategien
- Beste Strategie: Ohne Metadata + Hybrid Queries.
- jeden Query-Typ auswerten

## Erklärung von Performance-Unterschieden
- Einfluss von Metadaten und Query Refinement
- Beispiel
- Metadaten machen Suche schlechter
- Refined Queries helfen
- LLM tendiert zur Reproduktion von Train-Prompts bei langen Prompts *(schwer zu erklären)*

# Limitationen
- Benchmark hardware-technisch beschränkt (GPU hat nicht genug VRAM oder Modelle wie DeepSeek sind laut LLM Benchmark sehr gut aber zu groß)
- Programm funktioniert schlecht auf ressourcenbeschränkten Geräten
- Benchmark nur von einer Person annotiert/erstellt => Risiko von Bias oder Fehlern
- wenn die LLM-Umschreibung von Suchanfragen falsch ist sind die Ergebnisse fast immer falsch


# Zusammenfassung und Ausblick


# Literaturverzeichnis
