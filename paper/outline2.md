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
- Vergleich verschieder Konfigurationen und Suchstrategien wie Query-Refinement oder Metadatenintegration, anschließende Evaluation durch Benchmark
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
- soll ich Transformer "from scratch" erklären oder overkill?

## ChromaDB *(passt der Titel?)*
- "from scratch" erklären oder mit vorherigem Unterkapitel mergen?
- z.B. "https://aclanthology.org/2024.findings-emnlp.470.pdf" geht nur kurz darauf ein

## Verwandte Arbeiten
- Gao, G., Ju, H., Jiang, J., Qin, Z., & Dong, B. (2024). A semantic search engine for Mathlib4. arXiv preprint arXiv:2403.13310.
- FindFacts


# Methodik
### Programmaufbau
- benötigt fertigen FindFacts-Index (= Solr-DB), d.h. baut darauf auf
- lädt aus der Solr-DB nur Dokumente mit dem "command" theorem/lemma/corollary
- ...

# Implementierung des Benchmarks
## Datenbasis 
## Verwendete Metriken
- jede Metrik als Formel erklären => was sagt diese Metrik aus?

# Evaluation und Analyse
## Vergleich der Konfigurationen

# Diskussion und Limitationen

# Zusammenfassung und Ausblick

# Literaturverzeichnis
