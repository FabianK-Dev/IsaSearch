# IsaSearch for PIDE AI

An extension of [PIDE AI](https://github.com/kappelmann/isabelle-pide-ai) that offers the
semantic search of IsaSearch to agents as the tool `isasearch`, with the agent skill
[`skills/isasearch`](skills/isasearch/SKILL.md). It is an Isabelle/Scala component of its own,
which needs PIDE AI and the IsaSearch component [`../isabelle`](../isabelle); PIDE AI itself
needs no change.

The tool runs the search in a server of the IsaSearch component, `isabelle isasearch_server`,
which it starts as a process of its own on the first call and stops with PIDE AI: as with
FindFacts, Solr and Lucene stay off the classpath of Isabelle's JVM. The first call takes a few
seconds for that server and its query embedder; later calls take under a second. Results
link to their sources on this machine (`local_file`, `local_line`, where the AFP is
registered or the file is in the Isabelle distribution) and online (`online_url`,
`entry_url`). With a running session, every hit
says whether that session can use it (`availability`): its theory is loaded in the base
session, the session can load it from its sources, or its session (usually an AFP entry) is
missing.

## Install

Requirements: Isabelle2026, PIDE AI from its branch `main` (which works with Isabelle2026),
llama.cpp (`llama-server` on `PATH`), 16 GB of memory and about 11 GB of disk for the index
and the embedding model.

1. Register the three components, from the root of this repository and of the PIDE AI
   clone:

   ```sh
   isabelle components -u /path/to/isabelle-pide-ai
   isabelle components -u "$PWD/isabelle"
   isabelle components -u "$PWD/pide_ai"
   ```

2. Install the index of a [release](https://github.com/FabianK-Dev/IsaSearch/releases): download
   all parts, then unpack and install them (seconds; see `isabelle/runs/isabelle2026-gemma4`):

   ```sh
   cat isasearch-plain-*.tar.zst.* | zstd -d | tar -x
   isabelle isasearch_import -f isasearch-plain -i plain
   ```

3. Give the agent the skill: copy `skills/isasearch` next to PIDE AI's skills, e.g. into
   `~/.claude/skills`, `~/.config/opencode/skills` or `~/.agents/skills`. PIDE AI's own
   `pide-ai` skill tells agents to load the skills of extensions.

4. Start PIDE AI as usual (`isabelle pide_mcp ...` or `isabelle pide_ai ...`). The tool is
   served by default; PIDE AI's options `pide_ai_tools_include` and `pide_ai_tools_exclude`
   select tools by name.

The search uses the configuration and index of the IsaSearch component: Isabelle options
`isasearch_config` (default `isabelle/etc/search.json`, a local embedder) and `isasearch_index`
(default `plain`). Query expansion (`"expand": true`) works once the configuration enables it,
e.g. `llamacpp_query_server` in `search.json` (see `isabelle/README.md`).

## Notes

- The search server's output goes to the log of PIDE AI, prefixed `isasearch_server:`. If it
  stops, the next call starts it again.
- The tool follows the index: after `isabelle isasearch_import` publishes a new generation, the
  next search uses it.
- Packages generate facts that have no source of their own (`list.induct`, `foo.simps`); the
  index does not contain them. `find_theorems` and PIDE AI's `find_entities` do.
- Results are compact unless the call asks for `details`: names, theory, AFP entry, `context`
  (the locale or class qualifier of the name), statement, distance, availability and the local
  source, or the online source where there is no local one. Copies of a statement are one hit
  (`copies`), represented by the copy the session can use best.
- `available` (`loaded`, `known`), `source`, `entries` and `mentions` narrow the search. The
  tool turns availability into the AFP entries (selected before ranking) and sessions (checked
  on the nearest documents) of the running session for the search server, and checks every
  hit against it.
