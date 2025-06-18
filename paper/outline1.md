# KI-gestützte Theoremsuche in Isabelle: Ein transformerbasierter Ansatz

## Einleitung
### Bedeutung effizienter Theoremsuche
- Isabelle: generischer interaktiver Theorembeweiser mit besonderem Schwerpunkt auf Higher-Order Logic
- formale Verifizierung von Hard- und Software
- AFP: peer-reviewte Datenbank von Beweisbibliotheken
- stetig wachsende Zahl an Einträgen und formalen Theoremen im AFP (Quelle: Mining the Archive of Formal Proofs", https://www.isa-afp.org/statistics/ (darf ich das zitieren?))
- Wiederverwendung bestehender Theorem essenziell um Duplikate zu vermeiden => zu wenig (Quelle: Mining the Archive of Formal Proofs" > Conclusion)

### Problemstellung & Zielsetzung
- Suchmaschinen wie isa-afp.org oder FindFacts oder Befehle wie find_theorems oder grep erlauben nur lexikalische Suche => keine Semantische Suche
- Keine Treffer bei abweichenden Begriffen oder Reihenfolge der Begriffe
- Keine Ähnlichkeitserkennung oder intelligentes Ranking der Suchergebnisse
- Schwierig für Nutzer bestehende Theoreme wider zu finden
- gleichzeitig aber: Potential aktueller KI-Modelle für semantisches Retrieval
- Ziel: Entwicklung und Evaluation einer KI-gestützten semantischen Suche nach Theoremen, Lemmas und Corollaries im AFP
- Verwendung vortrainierter Transformer-Modelle in Form von LLM zur Textgenerierung, Bi-Encoder zur Ähnlichkeitssuche und ChromaDB zur effizienten Speicherung und Vektorsuche
- Vergleich verschieder Konfigurationen und Suchstrategien wie Query-Refinement oder Metadatenintegration, anschließende Evlauation durch Benchmark
- Entwicklung der restAPI und Webseite

### Forschungsfragen
- Wie effektiv sind LLMs bei der Umschreibung von formalen Theoremen, um deren Auffindbarkeit durch Suchanfragen des Nutzers zu verbessern?
- Wie wirkt sich das Optimieren einer Suchanfrage durch LLMs oder das Einbetten von Metadaten eines entsprechenden Theorems, wie Titel oder Abstract des Entries, auf die Suchqualtität aus?
- Wie effektiv ist die Theoremsuche laut des Benchmarks und wie robust ist sie gegenüber simulierten Fehlern bei Suchanfragen?

### (optional: Aufbau der Arbeit?)


## Hintergrund
- Isabelle (Wiederholung?)
- AFP (Wiederholung?)
- Theoreme in der formalen Verifikation
- Was ist ein Theorem?
- Bedeutung in der formalen Verifikation?
- Lexikalische Suche vs. Semantische Suche
- Transformer-Architektur erklären


## Methodik
### Programmaufbau
### Suchstrategien
### Benchmark
### Evaluationsmetriken


## Evaluation & Diskussion
### Gesamtergebnis
### Analyse nach Query-Typ
### Beste Konfiguration & Interpretation
### Einzelfallanalyse


## Fazit & Ausblick
### Zusammenfassung
### Grenzen der Arbeit
### Ausblick
