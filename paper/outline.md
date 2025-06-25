# Titel: KI-gestützte Theoremsuche in Isabelle: Ein transformerbasierter Ansatz

- [Titel: KI-gestützte Theoremsuche in Isabelle: Ein transformerbasierter Ansatz](#titel-ki-gestützte-theoremsuche-in-isabelle-ein-transformerbasierter-ansatz)
- [1. Einleitung](#1-einleitung)
  - [1.1. Motivation \& Problemstellung](#11-motivation--problemstellung)
  - [1.2. Zielsetzung](#12-zielsetzung)
  - [1.3. Forschungsfragen](#13-forschungsfragen)
  - [1.4. (optional: Aufbau?)](#14-optional-aufbau)
- [2. Hintergrund](#2-hintergrund)
  - [2.1. Isabelle, AFP und formale Beweise](#21-isabelle-afp-und-formale-beweise)
  - [2.2. Bestehende Suchmechanismen](#22-bestehende-suchmechanismen)
  - [2.3. Transformerbasierte Sprachmodelle](#23-transformerbasierte-sprachmodelle)
  - [2.4. ChromaDB](#24-chromadb)
  - [2.5. Verwandte Arbeiten](#25-verwandte-arbeiten)
- [3. Methodik](#3-methodik)
  - [3.1. Programmaufbau](#31-programmaufbau)
  - [3.2. Informalisierung der Theoreme](#32-informalisierung-der-theoreme)
- [4. Benchmark](#4-benchmark)
  - [4.1. Aufbau des Benchmarks](#41-aufbau-des-benchmarks)
  - [4.2. Benchmark-Pipeline und Vergleich der Suchstrategien](#42-benchmark-pipeline-und-vergleich-der-suchstrategien)
  - [4.3. Verwendete Metriken](#43-verwendete-metriken)
- [5. Ergebnis und Analyse](#5-ergebnis-und-analyse)
  - [5.1. Vergleich der Suchstrategien](#51-vergleich-der-suchstrategien)
  - [5.2. Erklärung von Performance-Unterschieden](#52-erklärung-von-performance-unterschieden)
- [6. Limitationen](#6-limitationen)
- [7. Zusammenfassung und Ausblick](#7-zusammenfassung-und-ausblick)
- [8. Literaturverzeichnis](#8-literaturverzeichnis)

# 1. Einleitung

## 1.1. Motivation & Problemstellung
- Isabelle: generischer interaktiver Theorembeweiser mit besonderem Schwerpunkt auf Higher-Order Logic
- formale Verifizierung von Hard- und Software
- AFP: peer-reviewte Datenbank von Beweisbibliotheken
- stetig wachsende Zahl an Einträgen und formalen Theoremen im AFP (Quelle: Mining the Archive of Formal Proofs", https://www.isa-afp.org/statistics/ **(Frage: Darf ich die Statistik mit der Anzahl der Theoreme im AFP zitieren?) -> Ja**)
- Wiederverwendung bestehender Theorem essenziell um Duplikate zu vermeiden => zu wenig (Quelle: Mining the Archive of Formal Proofs" > Conclusion)
- Suchmaschinen wie isa-afp.org oder FindFacts oder Befehle wie find_theorems oder grep erlauben nur lexikalische Suche => keine Semantische Suche
- wird bei Nutzern (laut Studie) als störend empfunden
- Keine Treffer bei abweichenden Begriffen oder Reihenfolge der Begriffe
- Keine Ähnlichkeitserkennung oder intelligentes Ranking der Suchergebnisse
- Schwierig für Nutzer bestehende Theoreme wieder zu finden
- gleichzeitig aber: Potential aktueller KI-Modelle für semantisches Retrieval

## 1.2. Zielsetzung
- Ziel: Entwicklung und Evaluation einer KI-gestützten semantischen Suche nach Theoremen, Lemmas und Corollaries im AFP
- Verwendung vortrainierter Transformer-Modelle in Form von LLM zur Textgenerierung von Theorem-Beschreibungen und Optimieren einer Suchanfrage, ~~Bi-Encoder zur Ähnlichkeitssuche und ChromaDB zur effizienten Speicherung und Vektorsuche~~ **(Hier noch keine konkreten Technologien, das kommt dann in deiner Methodik)**
- Vergleich verschiedener Suchstrategien wie LLM-Umschreibung von Suchanfragen oder Metadatenintegration, anschließende Evaluation und Analyse durch Benchmark
- Entwicklung einer Weboberfläche zur Nutzung deiner Suche

## 1.3. Forschungsfragen
- Wie effektiv sind LLMs bei der Umschreibung von formalen Theoremen, um deren Auffindbarkeit durch Suchanfragen des Nutzers zu verbessern?
- Wie effektiv ist die Theoremsuche ~~laut des Benchmarks~~ und wie robust ist sie gegenüber ~~simulierten~~ fehlerhaften Suchanfragen?
- Wie wirkt sich das Optimieren einer Suchanfrage durch LLMs oder das Einbetten von Metadaten eines entsprechenden Theorems, wie Titel oder Abstract des Entries, auf die Suchqualtität aus?

## 1.4. (optional: Aufbau?)


# 2. Hintergrund

## 2.1. Isabelle, AFP und formale Beweise
- **(Frage: Soll ich mich hier wiederholen? Ich erkläre in *Motivation & Problemstellung* ja schon, was das AFP und Isabelle ist) -> Nicht wiederholen, aber etwas mehr Details liefern als in der Einleitung**
- Isabelle
- AFP: besteht aus Entries, die aus formalen Theoremen, Definitionen, Beweisen, etc. bestehen
- außerdem: Paper mit Title, Abstract

## 2.2. Bestehende Suchmechanismen
- **(Frage: Soll ich mich hier wie oben wieder wiederholen) -> Auch hier: Nicht wiederholen, aber hier mehr im Detail erklären wie die anderen Suchen funktionieren und wie sie sich voneinander und deinem Ansatz unterscheiden**
- **Und das würde ich mit den verwandten Arbeiten verbinden**
- FindFacts, isa-afp.org, find_theorem, grep?
- Was ist FindFacts? Wie funktioniert die bisherige Suche?
- aber: unterstützen jeweils nur lexikalische Suche, keine Semantische Suche

## 2.3. Transformerbasierte Sprachmodelle
- **(Frage: soll ich Transformer "from scratch" erklären oder ist das zu viel?) -> Maximal 1 Seite würde ich dazu schreiben**
- **Wichtig ist die grundsätzliche Funktionsweise und dabei auf das fokussieren, was du benötigst**

## 2.4. ChromaDB
- **(Frage: soll ich ChromaDB erklären oder nur kurz erwähnen/erklären?)**
- z.B. "https://aclanthology.org/2024.findings-emnlp.470.pdf" geht nur kurz darauf ein
- Ich persönlich finde fast, dass ein eigenes Unterkapitel zu viel dafür ist :) **-> Ich würde allgemeiner kurz über relevante Datenbanken reden und dann in der Methodik auf ChromaDB eingehen und erklären wieso das relevant ist.**

## 2.5. Verwandte Arbeiten
- Gao, G., Ju, H., Jiang, J., Qin, Z., & Dong, B. (2024). A semantic search engine for Mathlib4. arXiv preprint arXiv:2403.13310.
- Huch, F., & Krauss, A. (2022). FindFacts: a scalable theorem search. arXiv preprint arXiv:2204.14191.
- genügen 2 Verwandte Arbeiten? **-> Wenn du mehr findest, gerne mehr. Du musst aber nicht alle detailliert erklären**


# 3. Methodik

## 3.1. Programmaufbau
- Detaillierte Schritt-für-Schritt Erklärung des Programm-Ablaufs, z.B.:
- benötigt fertigen FindFacts-Index, d.h. baut darauf auf
- verbindet sich mit bereits laufender Solr-Datenbank
- lädt aus der Solr-DB nur Dokumente mit dem "command" theorem/lemma/corollary
- prüft für jedes Theorem, ob dieses bereits vom in der config festgelegten LLM beschrieben informalisiert wurde
- auch z.B. auf Caching und Standard-Konfiguration eingehen
- Generierte LLM-Outputs werden gespeichert und können committet werden, um zu verhindern, das andere Nutzer die selben Outputs nochmal generieren müssen
- ...
- bei einer Suchanfrage: LLM umschreibt die Suchanfrage, um die Suchqualität zu verbessern (optional und kann deaktiviert werden)
- startet Flask-API-Server zur Bereitstellung einer REST-API

## 3.2. Informalisierung der Theoreme
- was ist "Informalisierung" der Theorem?
  - => LLM umschreibt den Theorem-Code in informale Sprache, damit es leichter zum Finden ist
- warum ausgerechnet das LLM microsoft/Phi-3.5-mini-instruct?
  - => technische Limitationen
  - => Wahl anhand von LLM Leaderboard
- Beispiel: Prompt, Input Theorem, Umschreibung
- **(Frage: Prompt-Beispiel lieber hier oder in den Anhang mit Referenz?)**
- **Ein kleines Beispiel gerne hier, wenn's zu lang wird (länger als ca. 1/3 Seite dann lieber in den Anhang)**


# 4. Benchmark

## 4.1. Aufbau des Benchmarks
- Quelle: Freek's "Top 100 Theorems in Isabelle"
- Struktur der Benchmark-Tabelle: ID, Title, Theorem, Target Identifiers, Link, Session, Annotation als CSV
- **Frage: soll ich jede column erklären? -> Nur die, die wichtig zum verstehen sind wie der Benchmark funktioniert**
- Generierung der Queries: Title, Natural language query, noisy natural language query
- Erklärung der Query-Arten und wie sie erstellt wurden (z.B. Zitat aus Wikipedia)
- Beispiel für Query Arten und Ziel Theoreme

## 4.2. Benchmark-Pipeline und Vergleich der Suchstrategien
- Ablauf des Benchmarks erklären
- Verschiedene Suchstrategien erklären:
  - Theorem-Embeddings ohne Metadaten + LLM-Suchanfragen-Umschreibung
  - Theorem-Embeddings mit Metadaten + LLM-Suchanfragen-Umschreibung
  - Theorem-Embeddings ohne Metadaten ohne LLM-Suchanfragen-Umschreibung
  - Theorem-Embeddings mit Metadaten ohne LLM-Suchanfragen-Umschreibung
  - Theorem-Embeddings ohne Metadaten + Hybrid (Query + LLM-Suchanfragen-Umschreibung)
  - Theorem-Embeddings mit Metadaten + Hybrid (Query + LLM-Suchanfragen-Umschreibung)

## 4.3. Verwendete Metriken
- jede Metrik als Formel erklären => was sagt diese Metrik aus?


# 5. Ergebnis und Analyse

## 5.1. Vergleich der Suchstrategien
- Beste Strategie: Ohne Metadata + Hybrid Queries.
- jeden Query-Typ auswerten, d.h. die durchschnittlichen gemessenen Werte für jede Metrik für jede Query beschreiben

## 5.2. Erklärung von Performance-Unterschieden
- Einfluss von Metadaten und Query Refinement
- Beispiel
- Metadaten machen Suche schlechter
- Beispiel
- Refined Queries helfen
- Beispiel
- LLM tendiert zur Reproduktion von Train-Prompts bei langen Prompts (schwer zu erklären, warum)
- wenn die LLM-Umschreibung von Suchanfragen falsch ist sind die Ergebnisse fast immer falsch/schlecht => Beispiel


# 6. Limitationen
- Benchmark hardware-technisch beschränkt (GPU hat nicht genug VRAM oder Modelle wie DeepSeek sind laut LLM Benchmark sehr gut aber zu groß)
- Programm funktioniert schlecht auf ressourcenbeschränkten Geräten (z.B. Laptops)
- Die LLM-Umschreibung zu deaktivieren reduziert die Suchzeit erheblich und kann auf ressourcenbeschränkten Geräten helfen, reduziert aber auch die Suchqualität **(Frage: Soll ich hier fixe Werte z.B. 1,9 Sekunden Suchzeit nennen, auch wenn sie eigentlich hardware-abhängig und damit nicht konsistent sind?) -> Für einen Vergleich kann das interessant sein, bzw. um ein Gefühl zu bekommen ob es gut benutzbar ist oder nicht. Erklär dann aber auf jeden Fall dass die Werte von deinem Testsystem sind und gib die groben Specs.**
- Benchmark nur von einer Person annotiert/erstellt => Risiko von Bias oder Fehlern **Sehr gut, erwähn aber auch Einschränkungen die von deiner gewählten Liste von 100 Theorem kommen. Und im Ausblick da nochmal drauf eingehen**
- wenn die LLM-Umschreibung von Suchanfragen falsch ist sind die Ergebnisse fast immer falsch **Das ist klar, kannst du Gründe nennen bzw. wie man das vermeiden könnte?**


# 7. Zusammenfassung und Ausblick
- Zusammenfassung
- Idee für Zukunft: Nutzer bei Suchergebnissen fragen "sind diese Ergebnisse hilfreich?" => sowohl als Trainingsdaten um Bi-Encoder zu erweitern oder tatsächliche Suchqualität außerhalb des Benchmarks zu überprüfen
- KI-Suche kann z.B. in CI/CD-Pipelines oder pre-commit-hooks verwendet werden, um frühzeitig duplizierte Theoreme zu erkennen (im AFP gibt es schon einige Duplikate)


# 8. Literaturverzeichnis
