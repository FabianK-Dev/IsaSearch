---
name: isasearch
description: Semantic search of the theorems and definitions of the AFP and the Isabelle distribution through PIDE AI's isasearch tool. Use it to find existing facts or definitions by what they state when you do not know their names, before proving something that may already exist, or to discover which AFP entry formalizes a concept.
---

`isasearch` finds facts by meaning, not by name or pattern: every theorem and definition of the
AFP and the Isabelle distribution has an LLM-written description, and the query is matched
against those descriptions and the statements.

## When to use which search
- isasearch: you know what a fact says but not its name or form, e.g. "a finite union of
  countable sets is countable", or you look for a concept across the AFP ("Gröbner bases",
  "a verified SAT solver"). It also finds facts the running session cannot see yet.
- find_theorems (Isar command, via get_state) or PIDE AI's find_entities: you know a name, a
  constant or a term pattern, and the fact must be usable in the running session now. These
  see exactly the session's facts, including those that packages generate (`list.induct`,
  `foo.simps`), which isasearch does not index.

## Queries
- Describe the statement or concept in plain mathematical language; Isabelle notation and
  constant names are fine but not needed. One idea per query.
- `kind`: `theorems` (default) for lemmas, theorems and corollaries; `definitions` for
  definitions, functions, datatypes, records, locales, classes.
- Read the `statement` of a hit before you rely on it: a small `distance` means a close
  description, not an exact match. Rephrase or switch `kind` if the hits are off.
- `expand: true` lets an LLM paraphrase the query first. It helps vague or noisy queries, costs
  seconds per query, and fails if query expansion is not configured.

## Using a hit
- `theory` is session-qualified (e.g. `HOL-Library.Countable_Set`), `line` its start line in
  the indexed version; `names` are the facts or constants it defines.
- `local_file` and `local_line`: the file on this machine and the line of the hit there (the
  local version may differ; without `local_line` the file no longer contains the hit). Read
  it there, e.g. with PIDE AI's read tool. `online_url` and `entry_url` point to the AFP
  repository or the Isabelle library and the AFP entry page.
- `availability` (with a running session): `loaded` means its theory is in the session's base
  heap: import the theory (or one importing it) and use the fact. `known` means the session
  knows the theory's session and can load it from its sources: import it, which processes it
  first (slow for large sessions; a session started on that base is faster). `unavailable`
  means its session, usually the AFP entry `afp_entry`, is not known to the running session:
  it needs a session whose directories include that entry, or adapt the proof instead.

## Costs
The first call opens the index and starts a local embedding server (seconds; its very first
start downloads the embedding model, 4.3 GB). Later calls take about half a second.
