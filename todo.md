# To-do

## AI search
- [x] Choose specific model via config

## Benchmark
- [x] Maybe use Freek Wiedijk's 100 Theore  ms list (Wiedijk, F.: Formalizing 100 theorems, https://www.cs.ru.nl/~freek/100/) (of which about 90 are implemented in the AFP)
- [x] List of models to compare via config
- [x] Response time
- [x] Search query: more difficulty version of Natural Language Query
- [x] Mean Reciprocal Rank
- [x] Normalized Discounted Cumulative Gain?

### Comparisons
- one model: microsoft/Phi-3.5-mini-instruct (1)
- [x] with / without metadata (*2)
- [x] with / without LLM query refinement / hybrid (original query + refined query) (*3)
- total: 1*2*3 = 5 runs

## Deployment
- [x] Flask
- [x] UI with Bootstrap

## Optional
- [x] Docker image
- [x] ~~Pytests~~

## Sources

- [ ] **Build the AFP from its own sources instead of the GitHub mirror.** `config.json` currently
  tracks `https://github.com/isabelle-prover/mirror-afp-2025-2.git` on branch `master`, and
  `check_and_update` keeps it in sync with `git fetch` plus `git reset --hard`. Two problems, both
  observed during the first full-AFP build:
  - The mirror's `master` is **force-pushed**. A build run logged
    `+ f95f9664...a7c6f77d master -> origin/master (Aktualisierung erzwungen)`, i.e. the history
    the previous run built against no longer exists. What the corpus was built from is therefore
    not reproducible from the branch name alone.
  - The branch moves *while* it is being consumed, so a run can start against one state of the
    Archive and finish against another.

  (Note: the `Undefined fact` failures of `Detour_Calculus` and `Perrons_Formula` are *not* caused
  by the mirror. They are upstream breakage, introduced by Mercurial changeset `a094b05c15ec`
  "migration of Manuel's material to the repository" (2026-07-05), which modified exactly
  `Detour_Calculus.thy` and `Perron_Prerequisites.thy` and left the two facts undefined. Both the
  mirror and the Mercurial repository carry it, so switching sources does not fix them - they need
  excluding until upstream repairs them, and are worth reporting to the AFP maintainers.)

  The authoritative source is the Mercurial repository at
  `https://foss.heptapod.net/isa-afp/afp-2025-2` (already referenced by
  `afp_remote_thys_folder_url`). Two ways to get off the moving branch, cheapest first:
  - **A pinned release archive.** The AFP publishes per-release tarballs, and `installation.py`
    already installs Isabelle that way (`install_from_archive`, with checksum and identifier
    checks). Pointing the AFP component at an `archive_url` reuses that machinery, gives an
    immutable source, and drops the git dependency for it entirely. This is the smaller change and
    matches how Isabelle itself is pinned.
  - **Mercurial with a pinned revision**, if tracking the release branch between tarballs matters.
    Needs `hg` support in `check_and_update` next to the existing git path.

  Either way, record the exact revision or archive checksum in the run's report, so a corpus can be
  traced back to the sources it was built from.

## Informalization

- [ ] **Do not cut the statement at a fixed number of characters.** `statement_excerpt`
  (`src/documents.py`) is `strip_proof(src)[:config["theorem_max_length"]].strip()`, i.e. a plain
  slice at 1000 characters with no regard for where it lands. A long statement is therefore handed
  to the LLM broken off mid-string — a real run produced the description *"Due to the incomplete
  nature of the input (the theorem ends abruptly with `and \"`)"*, which is the good case; the bad
  case is a model that does not notice and describes a statement that was never there.

  This truncates the *input*, so it is worse than the output cut at `max_tokens`: the description is
  not merely missing its tail, it is about something incomplete. It also affects the duplicate
  detection, which shares `statement_excerpt` on purpose so that the judge compares the same text
  the description was generated from.

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
  the duplicate judge shares the excerpt via `statement_excerpt`, so either the judge sees the
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
  FindFacts — which is the same machinery the Isabelle/Scala component idea from the Zulip
  discussion would need anyway. A cheaper middle ground: mention the generated fact names inside
  the *generating* block's description, so "list.induct" is at least findable by name through
  the description text.

## Keeping the corpus current

- [ ] **Rebuild in the background when the AFP moves, and swap the result in when it is finished.**
  Today a corpus is only as current as the last manual `python3 -m src.corpus`, and bringing it up
  to date means a maintenance window: the web application has to be stopped, because the build is
  the one process that may write and a serving process reads the same artifacts. For an Archive
  that gains entries continuously that is the wrong shape — and the update is usually small, since
  descriptions are keyed by a checksum of the source and only changed or new documents are
  informalized.

  What it needs, roughly:
  - **A trigger.** Poll the AFP for new commits (or watch it) rather than rebuilding on a timer, so
    a quiet week costs nothing.
  - **Somewhere to build that is not what is being served.** The build writes the document index,
    the descriptions artifact and the ChromaDB collections in place, so a background rebuild needs
    its own `cache_folder`, `artifacts_folder` and `chroma_db_path` — the config already makes all
    three configurable, so this is mostly a matter of pointing a second config at a second set of
    paths.
  - **An atomic swap.** Once the rebuild succeeds, the serving process has to start reading the new
    corpus. Simplest is the same trick `save_llm_output_cache` already uses: build beside the live
    copy, then move into place, then have the application reload. Note the application reads its
    corpus once at start-up, so today "reload" means a restart; a swap without one needs the
    corpora (see `components["corpora"]`) to be replaceable at runtime.
  - **A gate before swapping.** A rebuild that failed halfway must never become the served corpus.
    The duplicate detection's positive control is a ready-made check — every document has to
    retrieve itself at a distance of about 0 — and the run already exits non-zero when it does not.

  Note that the FindFacts index is the awkward part: `isabelle find_facts_index` writes the same
  Lucene index a running Solr holds open, so that step cannot simply run beside the live one. It
  needs its own Solr home and its own container, swapped the same way as the rest.

## Build ergonomics

- [ ] **Start Solr without asking during a corpus build.** `connect_solr` asks
  "Solr seems to be down. Do you want to start a local Solr instance via Docker? [Y/n]"
  whenever it runs in a terminal. For the web application that question is reasonable; for
  `python3 -m src.corpus` it is not: the question comes right after the indexing phase, i.e.
  hours into an unattended run, and the pipeline then blocks at the prompt until a human
  reattaches the tmux session and presses Y - observed repeatedly during the full-AFP builds,
  where it cost idle hours each time. A build that was started deliberately has already answered
  the question; there is nothing left to ask.

  Sketch: a config key (e.g. `"solr_autostart": true`) consulted before prompting - when set,
  `connect_solr` starts the local Solr directly and only falls back to the question when the key
  is absent and stdin is a terminal. The non-interactive path must keep its current behaviour of
  raising instead of prompting (a deployed process has no terminal, and that guard exists for a
  reason - see the SolrConnectionTest cases). Alternatively the corpus entry point could pass an
  "autostart" intent down to connect_solr explicitly, which keeps the decision per entry point
  rather than global.

## Indexing

- [ ] **Incremental FindFacts indexing.** Every index build starts from zero, and that is the
  tool's doing, not ours: `find_facts_index` hardcodes `clean = true` when it opens the Solr
  database (`src/Tools/Find_Facts/src/find_facts.scala`, `find_facts_index`), and neither its
  usage nor any system option offers a way around it - verified against Isabelle2025-2. The
  irony is that the incremental machinery already exists two screens up in the same file and
  runs on every build: `delete_session` clears a session before it is re-indexed and
  `update_theory` diffs per-theory block domains. Only the CLI entry point wipes first.
  Realistic fix: an upstream patch that makes `clean` an option (index the named sessions into
  the existing database, `delete_session` handles replacement; dropped sessions need explicit
  removal). Until then, our delete-and-rebuild in `build_index` merely mirrors what the tool
  does anyway, and the hours per rebuild are the price of any session-list change.

- [ ] **An AFP content update does not re-index.** `build_index` skips when the index exists and
  the *session list* is unchanged - the state file compares names, not content. An AFP pull that
  modifies existing entries without adding any (the common case for a release mirror taking
  fixes) therefore changes nothing in the index: Solr keeps serving the old blocks, the document
  fetch reads them, and the corpus quietly diverges from the checkout while the README's update
  section claims otherwise. The fingerprint downstream (document count) can even match, hiding
  it completely. Fix ideas: include a content hash (e.g. the AFP checkout's git commit) in the
  state file next to the session list, so a moved checkout triggers a rebuild - which today
  means a full one, and is what makes the incremental indexing above worth having first.
