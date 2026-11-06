---
name: isasearch
description: Semantic search of the theorems and definitions of the AFP and the Isabelle distribution through PIDE AI's isasearch tool. Use it to find existing facts or definitions by what they state when you do not know their names, before proving something that may already exist, or to discover which AFP entry formalizes a concept.
---

`isasearch` finds facts by meaning, not by name or pattern: every theorem and definition of the
AFP and the Isabelle distribution has an LLM-written description, and the query is matched
against those descriptions.

## When to use which search
- isasearch: you know what a fact says but not its name or form, e.g. "a finite union of
  countable sets is countable", or you look for a concept across the AFP ("Gröbner bases").
  It also finds facts the running session cannot see yet. It indexes single facts and
  definitions, not whole developments: for "a verified SAT solver" expect scattered lemmas.
- find_theorems (Isar command, via get_state) or PIDE AI's find_entities: you know a name, a
  constant or a term pattern, and the fact must be usable in the running session now. These
  see exactly the session's facts, including those that packages generate (`list.induct`,
  `foo.simps`, introduction rules), which isasearch does not index as facts of their own: a
  hit of the generating command (`fun`, `inductive`, `datatype`) lists their names.

## Queries
- Describe the statement or concept in plain mathematical language. Queries in Isabelle
  notation match worse, since the descriptions are prose and sources vary in notation
  (`sum_list` vs `∑x←xs`). One idea per query.
- `kind`: `theorems` (default) for lemmas, theorems and corollaries; `definitions` for
  definitions, functions, datatypes, records, inductive predicates, locales, classes.
- Narrow the search rather than reading more hits:
  - `available: "loaded"` (only facts the running session has loaded) or `"known"` (also those
    it can load from sources). Start with `"loaded"` when proving inside what you import.
  - `source: "distribution"` or `"afp"`, and `entries: ["Groebner_Bases"]` for AFP entries.
  - `mentions: ["countable", "⋃"]`: the statement must contain each, a name as a whole name,
    a symbol as text (`\<Union>` works too).
- Read the `statement` of every hit you use: descriptions are LLM-written and sometimes wrong
  (e.g. a Greibach normal form described as Gröbner), and distances of right and wrong hits
  are close. Rephrase or switch `kind` if the hits are off.
- `expand: true` lets an LLM paraphrase the query first. It is off unless query expansion is
  configured, which it is not by default; then the call fails.

## Using a hit
- `theory` is session-qualified (e.g. `HOL-Library.Countable_Set`); `names` are the facts or
  constants it declares, generated ones as `f.simps` rather than `f.simps(2)`, at most 20, with
  `more_names` counting the rest.
- `context`: the qualifier of its name between theory and fact, usually the locale or class
  it is stated in (`gd_term` for `Reduced_GB.gd_term.is_reduced_GB_unique`). A locale fact needs
  an interpretation of that locale (or a proof inside `context gd_term begin`); a class fact
  holds for every instance of the class. Check the source if unsure, as it may also be a name
  space.
- `copies`: the same statement elsewhere, e.g. AFP copies of HOL theories or restatements under
  another name, with their theory and availability. The hit shown is the most available copy.
- `local_file` and `local_line`: the file on this machine and the line of the hit there (the
  local version may differ; without `local_line` the file no longer contains the hit). Read
  it there, e.g. with PIDE AI's read tool. Without a local file, `line` and `online_url` locate
  it in the indexed version.
- `details: true` adds the description, every name, the command and the online links
  (`online_url`, `entry_url`) to each hit; leave it off unless you need them.
- `availability` (with a running session): `loaded` means its theory is in the session's base
  heap: import the theory (or one importing it) and use the fact. `known` means the session
  knows the theory's session and can load it from its sources: import it, which processes it
  first (slow for large sessions; a session started on that base is faster). `unavailable`
  means its session, usually the AFP entry `afp_entry`, is not known to the running session:
  it needs a session whose directories include that entry, or adapt the proof instead.

## Costs
The first call opens the index and starts a local embedding server (seconds; its very first
start downloads the embedding model, 4.3 GB). Later calls take about half a second.
