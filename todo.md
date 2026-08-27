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
