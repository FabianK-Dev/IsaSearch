# To-do

## Deployment

- [ ] **Serve theory pages from the Isabelle component.** The website of `isasearch_server`
  links results to the online Isabelle library and AFP pages, so a local server still needs the
  network to show a theory. Isabelle has the pieces: `HTTP.Browser_Info` serves theory pages from
  a File_Store database by path, and every result already carries that path in `url_path`
  (e.g. `AFP/Mersenne_Primes/Lucas_Lehmer.html`). The FindFacts web server works the same way.

  Sketch, in two steps:
  1. Distribution theories. A release ships their pages in `$ISABELLE_BROWSER_INFO_LIBRARY`
     (`lib/browser_info.db`, 178 MB on the server; a development checkout has none). Mount
     `HTTP.Browser_Info` on it in `Search.server`, report in `/capabilities` whether it exists,
     and let the page link non-AFP results to `browser_info/` + `url_path`, keeping the online
     links otherwise. No change to builds or indexes.
  2. AFP theories. `Corpus_Build.export_sources` calls `Find_Facts.find_facts_index` with
     `browser_info = false`; with `true` FindFacts renders the HTML of every indexed session
     into a `browser_info.db` next to its Solr core. Make that a configuration option, because
     it renders all ~1,160 sessions whenever the FindFacts index is rebuilt. Generations are
     self-contained and relocatable, so the database belongs into each generation (interchange
     format, import, packaging) rather than being read from FindFacts' working directory at
     serve time. Measure the time and size on a few sessions first; the size is probably a few
     GB.

## Informalization

- [ ] **Do not cut the statement at a fixed number of characters.** The describe prompt
  (`Corpus_Build`, `isabelle/src/corpus.scala`) and the duplicate judge
  (`isabelle/src/duplicates.scala`) both take `truncate(strip_proof(src), theorem_max_length)`,
  i.e. a plain cut at a number of characters with no regard for where it lands. A long statement is therefore handed
  to the LLM broken off mid-string — a real run produced the description *"Due to the incomplete
  nature of the input (the theorem ends abruptly with `and \"`)"*, which is the good case; the bad
  case is a model that does not notice and describes a statement that was never there.

  This truncates the *input*, so it is worse than the output cut at `max_tokens`: the description is
  not merely missing its tail, it is about something incomplete. It also affects the duplicate
  detection, which shares the excerpt on purpose so that the judge compares the same text the
  description was generated from.

  Options, roughly in order of effort:
  - Raise `theorem_max_length` until almost nothing is cut. Input tokens are much cheaper than
    output tokens (prefill runs faster than generation), so this costs little; the limit is the
    per-slot context, which `--parallel` divides among the slots.
  - Cut at a boundary rather than a character count — the end of the last complete line, or of the
    last balanced `"..."` — so what the model receives is always a syntactically whole prefix.
  - Cut only what genuinely does not fit, i.e. derive the budget from the model's context window
    and the configured `max_tokens` instead of from a constant that has no relation to either.

  Whatever is chosen, a document whose statement had to be cut should be counted and reported, the
  way truncated completions now are — the current cut is silent, which is why it went unnoticed.

  Measured on the full corpus (302,873 theorem documents), so the cost of raising it is known:
  median statement 149 characters, 95th percentile 461, longest 19,960. The cap only bites on a
  long tail, which is why raising it is cheap — only the affected documents send longer prompts.

  | cap | statements still cut |
  | --- | --- |
  | 1000 (current) | 2,513 (0.83%) |
  | 2000 | 621 (0.21%) |
  | 3000 | 288 (0.10%) |
  | 5000 | 113 (0.04%) |

  Done: the cap is 3000 since the locale measurement below; the boundary-aware cut and the
  reporting remain open. Locales made the decision urgent - measured over the AFP, 7.2% of locale
  blocks exceed 1000 characters (median 219, p99 2619, max 6311), against 0.8-2% for the other
  definitional commands; at 3000 every category is below 1%.

  3000 removes 88% of the cut theorem statements for roughly an hour across a
  multi-day build. Higher mainly buys the thin tail, and long prompts start competing for the
  per-slot context, which `--parallel` divides among the slots — check `n_ctx` at the server's
  `/props` before going further. Note that raising the cap does not regenerate the descriptions
  that were already made from a cut statement: the checksum covers `src`, not the excerpt, so those
  entries have to be deleted by hand to be redone.

- [ ] **Show the LLM the enclosing locale when it describes a locale-interior document.**
  Lemmas and definitions inside a `locale`/`context` block are covered — each is its own outer
  command, so FindFacts gives it its own block — but the block is *just the statement*: the
  locale's `fixes` and `assumes` live in the locale's own header block and are not repeated. The
  informalization therefore describes `lemma add_commute: "a + b = b + a"` without ever seeing
  that it holds under the assumptions of, say, a commutative-group locale, and the description
  cannot mention hypotheses it was never shown. The statement is searchable and dedupable either
  way; its description is just less precise than the source allows.

  Sketch: the entity kname already names the enclosing locale (e.g.
  `Abstract_First_Goedel.Goedel_Form.goedel_first_theEasyHalf` is *theory.locale.name*), and the
  locale's header is itself a corpus document since the `locale` command was added to
  `solr_query_definitions` — so the header text could be looked up by kname and prepended to the
  describe prompt as context ("this statement is made inside the following locale: ...").
  Two costs to weigh: every locale-interior description changes, which re-informalizes a large
  part of the corpus (do it together with the next deliberate corpus rebuild, not casually), and
  the duplicate judge shares the excerpt, so either the judge sees the
  locale context too — probably an improvement, cross-locale near-twins get judged with their
  hypotheses visible — or the excerpt and the describe input stop being identical, which breaks
  the "judge sees what was informalized" invariant on purpose and must be documented.

  (Related, decided and fine: facts *generated* by `interpretation` are not separate documents —
  the locale-level original represents them. That is what keeps thousands of near-identical
  instantiation copies out of search results and the duplicate report.)

- [ ] **Decide whether package-generated lemmas and constants should be searchable.** The corpus
  is built from FindFacts *source blocks*, and a block exists only where a command stands in the
  theory text. The facts that Isabelle's definitional packages generate — `list.induct`,
  `t.simps`, `t.cases`, discriminators and selectors from `datatype`, `.intros` from `inductive`,
  `.psimps` from `function`, and so on — have no source line of their own, so none of them is a
  document: not searchable, not informalized, invisible to the duplicate detection. Only the
  generating command's block is in the corpus (and, for the definitions corpus, its Solr
  `consts`/`typs` fields do list the generated constant names, which is what the synthetic ground
  truth already keys on).

  A command facet over the full index (2026-09-04, 817,769 blocks) put numbers on the deliberate
  exclusions when the custom AOT/sepref/corec commands were added to the queries. Left out on
  purpose: alias bundles that restate existing facts (`lemmas` 14,345, `named_theorems` 755,
  `lemmas_with` 136) — including them would inject near-duplicates by construction; generated
  auxiliary lemmas whose block is a directive rather than a statement (`inductive_cases` 918,
  `termination` 693, `arity_theorem` 180, `inductive_simps` 147, `equivariance` 109,
  `sepref_thm` 105); entry-specific generator macros with no readable statement (`derive` 259,
  `mk_VLambda` 204, `synthesize` 145, `mk_ide` 143); SPARK proof obligations (`spark_vc` 54);
  and the Isabelle/DOF starred variants (`lemma*` 2, `definition*` 1), which would need
  wildcard-escaped Solr queries for a handful of documents.

  Whether that is a gap or a feature needs deciding before any implementing: a user searching
  "induction principle for rose trees" is well served by finding the `datatype rose_tree` block
  itself, and generated facts are numerous, mechanical and mutually near-identical — embedding
  hundreds of thousands of them would flood search results and the duplicate report with
  boilerplate (IsaFinder indexes them per entity and needed dedicated agent skills for datatype
  and intro/elim rules plus an infrastructure filter to keep that manageable). If they are added,
  it cannot be done with Solr queries: it needs an entity-level export out of Isabelle/ML (the
  theory's fact space, e.g. what `find_theorems` sees), i.e. a second export path next to
  FindFacts, which the Isabelle component could host beside its FindFacts export. A cheaper middle ground: mention the generated fact names inside
  the *generating* block's description, so "list.induct" is at least findable by name through
  the description text.

## Keeping the corpus current

- [ ] **Rebuild in the background when the AFP moves, and switch the server over when it is
  finished.** Most of the machinery exists: `isasearch_index` builds a new generation beside the
  published one, `Index.publish` switches `current.json` in one step, and a failed build or
  import never publishes, so the served index stays intact. Descriptions and embeddings are
  reused by checksum, so a small AFP update stays cheap. Two pieces are missing:
  - **A trigger.** Poll the AFP for new changesets (or watch it) rather than rebuilding on a
    timer, so a quiet week costs nothing.
  - **Picking up the new generation.** `isasearch_server` opens the index once at startup
    (`Index.current` in `isabelle/src/tools.scala`), so a new generation is served only after a
    restart. Either restart the server after a publish, or let `Search.Engine` notice a changed
    `current.json` and switch snapshots between requests, closing the old one once no search
    uses it. Old generations then need removing too: every build leaves one behind (about 6 GB
    for the AFP).

## Build ergonomics

- [ ] **Let the Isabelle component build an index without progress output.**
  `isabelle isasearch_index` prints a `Prepared N of TOTAL ...` line after every batch of 32
  documents, plus a description sample, and appends both to its log. While documents are read
  back from the stores (about 825 per second on the server) that is some 25 lines per second over
  the 515,000 documents of the AFP, and in tmux the output seemed to cost noticeable time. Once
  the build is stable it will run automatically, so nobody reads that output anyway.

  Sketch: a `-q` option that leaves out the per-batch progress and the samples. It keeps the
  phase lines (`Index ...`, `FindFacts index is current ...`), warnings, errors and the final
  summary of each corpus. Truncated and undescribed documents are already recorded in the
  manifest, so nothing is lost. Measure first: compare a run against one with its output sent
  to `/dev/null`, to see whether the printing or the store reads limit the rate. If the
  terminal is the cost, printing at most every few seconds instead of every batch may be enough
  without an option, or the per-batch lines could appear only with the existing `-v`.

## Indexing

- [ ] **Incremental FindFacts indexing.** Every index build starts from zero, and that is the
  tool's doing, not ours: `find_facts_index` hardcodes `clean = true` when it opens the Solr
  database (`src/Tools/Find_Facts/src/find_facts.scala`, `find_facts_index`), and neither its
  usage nor any system option offers a way around it - still so in Isabelle2026. The
  irony is that the incremental machinery already exists two screens up in the same file and
  runs on every build: `delete_session` clears a session before it is re-indexed and
  `update_theory` diffs per-theory block domains. Only the CLI entry point wipes first.
  Realistic fix: an upstream patch that makes `clean` an option (index the named sessions into
  the existing database, `delete_session` handles replacement; dropped sessions need explicit
  removal). Until then, `Corpus_Build.export_sources` re-indexes all sessions whenever its
  state file (`find_facts.json`: the FindFacts database and the build ID of every session)
  changes, so a single rebuilt session costs a full FindFacts index.
