# IsaSearch for PIDE AI

An extension of [PIDE AI](https://github.com/kappelmann/isabelle-pide-ai) that offers the
IsaSearch search to agents as the tool `isasearch`, with the agent skill
[`skills/isasearch`](skills/isasearch/SKILL.md). It is an Isabelle/Scala component of its own;
PIDE AI itself needs no change.

## Install

Requirements: those of the [quickstart](../QUICKSTART.md), and PIDE AI from its branch `main`.

1. Register PIDE AI and both components of this repository (from its root):

   ```sh
   isabelle components -u /path/to/isabelle-pide-ai
   isabelle components -u "$PWD/isabelle"
   isabelle components -u "$PWD/pide_ai"
   ```

2. Install the index: `isabelle isasearch_import` (see the quickstart).

3. Give the agent the skill: copy `skills/isasearch` next to PIDE AI's skills, e.g. into
   `~/.claude/skills`, `~/.config/opencode/skills` or `~/.agents/skills`. PIDE AI's `pide-ai`
   skill tells agents to load the skills of extensions.

4. Start PIDE AI as usual (`isabelle pide_mcp ...` or `isabelle pide_ai ...`). The tool is on
   by default; PIDE AI's options `pide_ai_tools_include` and `pide_ai_tools_exclude` select
   tools by name.

The tool uses the configuration and index of the IsaSearch component (options
`isasearch_config` and `isasearch_index`). Query expansion (`"expand": true`) works once the
configuration enables it (see [`isabelle/README.md`](../isabelle/README.md)).

## How it works

The tool runs the search in `isabelle isasearch_server`, which it starts on the first call and
stops with PIDE AI. As with FindFacts, this keeps Solr and Lucene off the classpath of
Isabelle's JVM. The first call takes a few seconds; later calls take under a second. The
server's output goes to PIDE AI's log, prefixed `isasearch_server:`; if it stops, the next call
starts it again. After `isasearch_import` publishes a new index, the next search uses it.

Results are compact unless the call asks for `details`: names, theory, AFP entry, `context`
(the locale or class qualifier of the name), statement, distance, availability, and the local
source (`local_file`, `local_line`) or else the online one. Copies of a statement are one hit
(`copies`), represented by the copy the session can use best.

With a running session, every hit says whether that session can use it (`availability`): its
theory is `loaded` in the base session, the session can load it from its sources (`known`), or
its session, usually an AFP entry, is `unavailable`. The filters `available`, `source`,
`entries` and `mentions` narrow the search; availability is turned into AFP entries (selected
before ranking) and sessions (checked on the nearest documents).

Facts that packages generate without a source of their own (`list.induct`, `foo.simps`) are not
in the index; `find_theorems` and PIDE AI's `find_entities` find them.
