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

- [ ] **Release the index on GitHub for laptops without a GPU.** Searching a prebuilt index needs
  only the index data and an embedder for the queries (`llm_backend: none` already works). The
  data is the obstacle: about 515,000 documents with 2560-dimensional float32 vectors of
  `Qwen3-Embedding-4B`, about 5.3 GB of vectors and about 6 GB per generation. The query embedder
  is not: the Q8_0 GGUF of the same model ranks as the server does and embeds a query in half a
  second on a laptop CPU (measurements in `isabelle/runs/isabelle2026-gemma4/README.md`).

  The channel is GitHub Releases of this repository, e.g. a tag
  `index-isabelle2026-afp2026-plain-v1`. Plain git rejects files above 100 MB and Git LFS meters
  storage and bandwidth; release assets may have up to 2 GiB each, with no limit on the total
  size or on downloads. Zenodo could mirror the release for a DOI that the paper cites.

  Sketch, in order:
  1. Done (2026-11-05): drift and benchmark of F16, Q8_0, Q6_K and Q4_K_M on an M2 Pro, in
     `isabelle/runs/isabelle2026-gemma4/README.md`. Q8_0 drifts no more than the server's own
     embedder, keeps the tolerance of 0.005 and ranks as the server does; Q6_K and Q4_K_M exceed
     the tolerance although their rankings stay close. The component's default configuration
     `isabelle/etc/search.json` searches with Q8_0 on localhost. Not measured: an x86 laptop
     and Ollama.
  2. Done (2026-11-06): builds record three short reference queries per corpus with their
     vectors in the manifest (`reference_embeddings`), and searches check the embedder against
     those instead of re-embedding two long documents per corpus; on the M2 Pro's CPU this took
     a search from 28 s to 8 s, JVM and server start included. Indexes built before still use
     the document check until they are rebuilt.
  3. Done (2026-11-05), without a new format version: `isasearch_export` writes the current
     generation as interchange (records and float32 vectors, 46 s for the AFP), and the release
     packs it with `tar | zstd -10` (8.2 GB to 5.0 GB) and splits it into parts below 2 GiB.
     Importing it again took 36.5 minutes on the M2 Pro while other work ran, and the
     re-imported index answers with the same top 20 and distances. The packaged database is no
     alternative: `isasearch_index_build` fails on this index with an `IllegalArgumentException`,
     because its Lucene vector files (3.99 GB for theorems, 1.28 GB for definitions) exceed
     what one `File_Store` entry holds. Done (2026-11-06): releases ship the generation itself
     (`isasearch_export` by default), which `isasearch_import` installs in seconds instead of
     indexing it for 36.5 minutes; it packs to the same 5.0 GB. The interchange export
     (`-F interchange`) stays for other Lucene versions and tools. Its import still commits
     every 256 documents on one thread, which only matters for that fallback now.
  4. Publish. Done: `isabelle/runs/isabelle2026-gemma4/update` releases every new state of the
     index with its parts, the manifest, `SHA256SUMS` and notes on download and import. Still
     open: the drift and benchmark results and the laptop setup in the notes, the hash of the
     official GGUF, and a NOTICE that covers the AFP and Isabelle sources in the documents
     (BSD/LGPL per entry) and the Gemma-generated descriptions (check Gemma's terms for
     redistributing outputs); `Qwen3-Embedding` is Apache-2.0.

  Later, if the measurements ask for it:
  - Lucene 9.12 offers `Lucene99HnswScalarQuantizedVectorsFormat`: the graph search reads int8
    vectors (about 1.3 GB instead of 5.3 GB in memory), the reranking still the float32 ones
    from disk. Compare its recall with the current format.
  - A small query encoder for older and 8 GB laptops, e.g. Intel machines without a GPU, where
    the 4B model needs some 2 s per query and about 4.8 GB. Train a student (a small BERT of
    ~30M parameters, or `Qwen3-Embedding-0.6B` with a projection to 2560 dimensions) to
    reproduce the 4B model's query vectors, so the document vectors and the index stay as they
    are (LEAF, arXiv 2509.12539: 97.7% of its teacher on BEIR). The targets are cheap: the
    stored descriptions read like queries, so embedding them with the `retrieve` prompt on the
    server gives 515,000 training pairs without generating anything. The small student trains
    in hours on the model server (Ryzen AI Max+ 395, 128 GB); the 0.6B one would take days. It
    runs behind the same `/v1/embeddings` endpoint as a GGUF, at a few milliseconds per query.
    Accept it only if the benchmark stays close to the 4B model; named theorems (title queries)
    are the likely weakness, which BM25 over descriptions and lemma names would cover. The
    fallback is re-embedding the corpus with `Qwen3-Embedding-0.6B` (1024 dimensions, about
    1 GB of vectors), about 90% of the 4B model on MTEB retrieval.
  - `isasearch_fetch -r TAG -i NAME`, which downloads the assets, checks them against the
    manifest and imports them in one step.

- [ ] **Try the PIDE AI extension with agents.** `pide_ai` in this repository offers the search
  as PIDE AI's tool `isasearch`, with an agent skill; it builds with PIDE AI's `main` and
  Isabelle2026 and runs the engine inside the PIDE AI server (opened on the first call, closed
  with the server). Ask Kevin whether the extension should live here or among his extensions.

  First feedback of an agent (2026-11-06, about 60 hits) and what came of it: compact results
  by default (`details` for descriptions, all names and online links), numbered fact selections
  folded into one name and at most 20 names, filters by availability, source, AFP entry and
  mentioned tokens, copies of a statement as one hit (the Zippy entry copies `List`, `Set`,
  `GCD`, `Limits`, `Binomial` and `Finite_Set` and outranked the HOL originals in 7 queries),
  and the locale or class qualifier of a hit's name as `context`. Still open from it: the items
  below on descriptions, notation queries, entry-level search, goal queries and generated facts;
  theorems and definitions in one call (item under "Search") would save agents a second call.

## Search

- [ ] **Search theorems and definitions together.** A search covers exactly one corpus:
  `Search.Engine.search` takes a single `Corpus_Kind` (`isabelle/src/search.scala`), the
  `/search` service reads one `kind` parameter, the website offers a Theorems/Definitions radio
  choice (`isabelle/web/index.html`), and `isasearch_search -k` rejects more than one kind
  (`isabelle/src/tools.scala`). A user who does not know whether the answer is a lemma or a
  definition has to search twice.

  Sketch: accept several kinds (`kind=theorems,definitions`, `-k all`, checkboxes on the
  website), search every selected corpus and merge the hits into one list ranked by score, each
  result marked with its kind. The open question is whether the scores are comparable: each
  corpus embeds the query with its own retrieve prompt (`Index.prompt(corpus.spec,
  Prompt.Retrieve)`), so the same query gets two different vectors and the cosine scores of the
  two corpora may sit at different levels. Check that on the benchmark queries before merging
  by raw score; otherwise normalize per corpus or interleave by rank. Query refinement also uses
  a prompt per corpus (`Prompt.Expand`), so a combined search either refines once per corpus
  or needs one shared refinement prompt.

- [ ] **Match notation and names, not only descriptions.** Queries in Isabelle notation do worse
  than prose (agent feedback: `card ...` and `sum_list ...` queries missed, the source writing
  `∑x←xs`), and a wrong description ranks its fact wrongly however right the statement is. A
  second signal from the statement would help both: BM25 over statements and names (cheap,
  Lucene has it; also the remedy for named-theorem queries noted under the small query
  encoder), or an embedding of the statement itself (a second vector per document, so a
  rebuild and twice the vectors). Merge the rankings, e.g. by reciprocal rank fusion, and
  measure on the benchmark, whose queries are prose: add notation queries first. The tool's
  `mentions` filter is the manual stopgap.

- [ ] **Search AFP entries as a whole.** "A verified SAT solver" returns scattered lemmas at
  distances 0.30-0.42, because the corpora hold single facts and definitions. Every record
  already carries its entry's metadata (title, abstract, date): a third corpus of entries,
  embedding title and abstract (about 1,000 documents, minutes to build), would answer such
  questions, and a combined search could offer entries next to facts.

- [ ] **Search from a goal.** Agents mostly look at a subgoal, not at prose. A tool argument
  with theory, line and subgoal could take the goal from PIDE and use it as the query. Measure
  first how goal text retrieves (it is notation, see above), with and without query expansion,
  which could turn a goal into prose.

- [ ] **Collapse restatements that differ in their terminal proof.** `collapse` merges hits with
  the same `Text_Preparation.statement`, which drops a structured `proof` but keeps `by ...`,
  so `lemma a: "P" by simp` and `lemma b: "P" by auto` stay apart. Cutting the statement at the
  first proof command needs Isabelle's outer syntax tokens rather than a regular expression; it
  would also sharpen the duplicate analysis and the informalization input, whose goldens and
  prompts change with it.

- [ ] **Expand queries with a smaller local model.** Local expansion behaves as on the server
  since 2026-11-06: `llamacpp_query_server` starts llama.cpp with the server's query model
  (Gemma 4 26B-A4B, QAT `UD-Q4_K_XL`) on the first expanded query, with the server's prompts
  and sampling parameters, and the default `etc/search.json` carries it disabled. That model is
  a 14 GB download; on an M2 Pro with 32 GB it kept about 5.4 GB resident (a mixture of
  experts touches only part of its weights), which 16 GB machines may not spare. Expansion
  pays off: the paper's run with Phi-3.5-mini at Q4_0 (3.8B) raised
  Hit@10 from 0.635 to 0.773 and MRR from 0.439 to 0.546 for about 1.4 s per query, and on the
  current corpus the original plus expanded query (`UR`) with Gemma 4 reached Hit@10 0.863 and
  MRR 0.613 against 0.811 and 0.577 without expansion (September index against the one of
  November, so only roughly comparable). Most of the gain is on noisy queries.

  The server's model locally reproduces the server's expansions closely (2026-11-06, eight
  queries: same first hit, 9 or 10 of the same top 10; see the run's README) at about 4 s per
  query on an M2 Pro. Still to measure on the laptop with the `UR` benchmark strategy: the
  whole benchmark, and one or two models of 1 to 4B parameters (e.g.
  Qwen3-1.7B and 4B, a small Gemma 4), with their latency on the CPU and on Metal. An expansion
  generates some 100 to 200 tokens, so a 4B model probably needs 10 to 20 s on an Intel CPU
  without a GPU; cap `max_tokens` accordingly. The expand prompt asks for a paraphrase plus an
  Isabelle statement; a small model may do better with only the paraphrase. A smaller model
  is then only another `hf_repo` in the configuration.

  Cheapest of all for Intel laptops: train the small query encoder (see "Release the index on
  GitHub") to map a raw query to the teacher's embedding of query plus expansion, so expansion
  costs nothing per query.

## Informalization

- [ ] **Fix the truncation issues.** Both ends of the description step still cut text:
  - Output: descriptions cut off at `max_tokens` (512) on every attempt are kept and listed as
    `truncated_descriptions` in the manifest. The build of 2026-11-06 reports 13 truncated
    theorem descriptions; the definitions build of 2026-11-05 reported one. Find out why
    these run long (a statement that is long, or a model that loops), then either raise
    `max_tokens` for them, retry with a prompt that asks for brevity, or cut at the last
    complete sentence, so that no description of the index ends mid-word.
  - Input: statements are cut at `theorem_max_length` characters before they reach the model
    and the duplicate judge (next item), silently and possibly mid-string.

  Done means: every build reports both kinds of cut, and an index of the AFP has none that a
  user can see in a description.

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

- [ ] **Find out why descriptions go wrong.** An agent found five wrong descriptions in about
  60 hits: `gnf` (Greibach normal form) described as Gröbner, `Brzozowski` (the minimisation
  construction) as a derivative and ranked first for a derivative query, `size_list_pointwise`
  as a sum lemma, `principal_ideal_domain.bezout` with real numbers and integers, and
  `countable_union_of_Union` as about countable sets. Each guesses from a name instead of reading
  the definitions it depends on. Candidates: the entry's title and abstract and the locale (next
  item) in the describe prompt, the definitions of the constants a statement uses, a check of
  description against statement by the duplicate judge's model, and the larger describe model.
  Measure on a sample with hand-checked descriptions before rebuilding.

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

  An agent's view (2026-11-06): the names of a hit of the generating command already list the
  generated facts (`deriv.induct`, introduction rules), so they are reachable in two steps;
  what is missing is matching their statements, e.g. `rtrancl_into_rtrancl` lost to AFP
  restatements of itself. Worth indexing in its view: introduction rules of inductive
  definitions, the induction rules of `function`, and the map/set/rel facts of datatypes
  (`list.set_map`), tagged as generated so that a search can leave them out; not `.cases`,
  `.exhaust`, `.inject`, `.distinct`, `.split`, `.size` or `.simps`.

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
