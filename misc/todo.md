# To-do

## Deployment

- [ ] **Serve theory pages from the Isabelle component.** The website of `isasearch_server`
  links results to the online Isabelle library and AFP pages, so a local server needs the
  network to show a theory. `HTTP.Browser_Info` serves theory pages from a File_Store database
  by path, and every result carries that path in `url_path` (e.g.
  `AFP/Mersenne_Primes/Lucas_Lehmer.html`), as in the FindFacts web server.

  Sketch, in two steps:
  1. Distribution theories. A release ships their pages in `$ISABELLE_BROWSER_INFO_LIBRARY`
     (`lib/browser_info.db`, 178 MB on the server; a development checkout has none). Mount
     `HTTP.Browser_Info` on it in `Search.server`, report in `/capabilities` whether it exists,
     and let the page link non-AFP results to `browser_info/` + `url_path`, keeping the online
     links otherwise. No change to builds or indexes.
  2. AFP theories. `Corpus_Build.export_sources` calls `Find_Facts.find_facts_index` with
     `browser_info = false`; with `true` FindFacts renders every indexed session into a
     `browser_info.db` next to its Solr core. Make that an option, since it renders all ~1,160
     sessions on every FindFacts rebuild. Generations are self-contained and relocatable, so
     the database belongs into each generation (interchange format, import, packaging), not
     read from FindFacts' working directory at serve time. Measure time and size on a few
     sessions first; probably a few GB.

- [ ] **Finish the index releases for laptops without a GPU.** Releases are published by
  `isabelle/runs/isabelle2026-gemma4/update` (parts, manifest, `SHA256SUMS`, notes), and
  `isabelle isasearch_import` without `-f` installs one. A laptop needs only the index (about
  515,000 documents with 2560-dimensional float32 vectors of `Qwen3-Embedding-4B`: 5.3 GB of
  vectors, about 6 GB per generation) and the Q8_0 GGUF as query embedder (measurements on an
  M2 Pro in `isabelle/runs/isabelle2026-gemma4/README.md`; not measured: an x86 laptop and
  Ollama). Still open:
  - A NOTICE for the released data: the AFP and Isabelle sources in the documents (BSD/LGPL
    per entry) and the Gemma-generated descriptions (check Gemma's terms for redistributing
    outputs); `Qwen3-Embedding` is Apache-2.0.
  - The hash of the official GGUF, and the drift and benchmark results, in the notes (they
    link `QUICKSTART.md` for the setup).
  - Zenodo could mirror a release for a DOI that the paper cites.

  Later, if the measurements ask for it:
  - Lucene 9.12's `Lucene99HnswScalarQuantizedVectorsFormat`: the graph search reads int8
    vectors (about 1.3 GB instead of 5.3 GB in memory), the reranking the float32 ones from
    disk. Compare its recall with the current format.
  - A small query encoder for older and 8 GB laptops, e.g. Intel machines without a GPU, where
    the 4B model needs about 4.8 GB and some 2 s per query. Train a student (a small BERT of
    ~30M parameters, or `Qwen3-Embedding-0.6B` with a projection to 2560 dimensions) to
    reproduce the 4B model's query vectors, so document vectors and index stay as they are
    (LEAF, arXiv 2509.12539: 97.7% of its teacher on BEIR). The stored descriptions read like
    queries, so embedding them with the `retrieve` prompt on the server gives 515,000 training
    pairs without generating anything. The small student trains in hours on the model server
    (Ryzen AI Max+ 395, 128 GB), the 0.6B one in days; it runs behind the same
    `/v1/embeddings` endpoint as a GGUF, at a few milliseconds per query. Accept it only if the
    benchmark stays close to the 4B model; named theorems (title queries) are the likely
    weakness, which BM25 over descriptions and lemma names would cover. Fallback: re-embed the
    corpus with `Qwen3-Embedding-0.6B` (1024 dimensions, about 1 GB of vectors, about 90% of
    the 4B model on MTEB retrieval).
  - The import of interchange data (`isasearch_export -F interchange`) commits every 256
    documents on one thread; this only matters for that fallback format.

- [ ] **Try the PIDE AI extension with agents.** `pide_ai` offers the search as PIDE AI's tool
  `isasearch`, with an agent skill; it builds with PIDE AI's `main` and Isabelle2026 and runs
  the engine inside the PIDE AI server. Ask Kevin whether the extension should live here or
  among his extensions.

  Still open from two rounds of agent feedback (2026-11-06):
  - `available`: keep `"any"` as default (`"loaded"` would hide 5 of 16 known answers in
    HOL-Library, HOL-Computational_Algebra and the AFP without a sign) but rank loaded hits up
    within a margin of about 0.03-0.05 (`IVT` lost to an AFP restatement by 0.05); with an
    explicit `"loaded"`, name the closest hit it dropped when that is much closer.
  - `mentions` matches source text, so qualified names match nothing and constants written
    with notation need their symbol (`∑x←xs` for `sum_list`); see "Match notation and names".
  - The items below on `context`, names, example theories, descriptions, notation queries,
    entry-level search, goal queries and generated facts; theorems and definitions in one call
    would save agents a second call.

## Search

- [ ] **Derive `context` from the fact, not from the first declared constant.**
  `Search.qualifier` (`isabelle/src/search.scala`) takes the qualifier of the first of `consts`,
  then `typs`, then `thms`. For package commands that is an internal constant: `datatype 'a tree`
  (HOL-Library.Tree) gets `raw_prod.tree.sum2.prod.Product_Type`, `typedef 'a multiset` gets
  `typerep_multiset_inst`, every `class` gets `class`. Take the qualifier only where the
  command stands inside a `locale`/`context`/`class` block (the kname of its main entity), and
  report none for top-level package commands.

- [ ] **Show a hit's useful names first.** The tool's `names` lists `consts`, `typs`, then
  `thms` and keeps 20, so a `datatype` hit shows BNF internals (`alg_tree`, `mor_tree`,
  `Rep_tree_IITN_tree`, `typerep_..._inst`) and cuts its constructors, `tree.induct` and
  `tree.simps` (`more_names` 87-206). Order by use: the declared type and constants, then
  facts users state or use (`.induct`, `.simps`, `.intros`, map/set/rel), internal names
  (`_IITN_`, `pre_`, `alg_`, `mor_`, `typerep`, `term_of`, `narrowing`, `random`,
  `full_exhaustive`) last or not at all.

- [ ] **Keep examples and unfinished statements out of the way.** Definition queries rank
  example theories above the library: the group of `HOL-ex.MonoidGroup` above the HOL-Algebra
  and HOL-New_Algebra locales, `BinTree` of `HOL-Nitpick_Examples.Refute_Nits` above
  `HOL-Library.Tree`. Statements ending in `oops` (no `names`) are hits too, e.g.
  `saturate_sat_preserving` of Ordered_Resolution_Prover. Mark example sessions (`HOL-ex`,
  `HOL-Examples`, `*_Examples`) and unproven statements in the records; rank them down or let
  a filter leave them out.

- [ ] **Search theorems and definitions together.** A search covers one corpus:
  `Search.Engine.search` takes a single `Corpus_Kind` (`isabelle/src/search.scala`), `/search`
  reads one `kind`, the website offers a Theorems/Definitions radio choice
  (`isabelle/web/index.html`), and `isasearch_search -k` rejects more than one kind
  (`isabelle/src/tools.scala`). A user who does not know whether the answer is a lemma or a
  definition searches twice.

  Sketch: accept several kinds (`kind=theorems,definitions`, `-k all`, checkboxes), search each
  corpus and merge the hits by score, each marked with its kind. Open question: are the scores
  comparable? Each corpus embeds the query with its own retrieve prompt
  (`Index.prompt(corpus.spec, Prompt.Retrieve)`), so the cosine scores may sit at different
  levels. Check on the benchmark queries before merging by raw score; otherwise normalize per
  corpus or interleave by rank. Query refinement also has a prompt per corpus
  (`Prompt.Expand`): refine once per corpus or share one prompt.

- [ ] **Match notation and names, not only descriptions.** Queries in Isabelle notation do worse
  than prose (agents' `card ...` and `sum_list ...` queries missed; the source writes
  `∑x←xs`), and a wrong description ranks its fact wrongly however right the statement is. A
  second signal from the statement would help both: BM25 over statements and names (cheap in
  Lucene; also covers named-theorem queries, see the small query encoder), or an embedding of
  the statement (a second vector per document: a rebuild and twice the vectors). Merge the
  rankings, e.g. by reciprocal rank fusion, and measure on the benchmark after adding notation
  queries to it (its queries are prose). The tool's `mentions` filter is the manual stopgap.

- [ ] **Search AFP entries as a whole.** "A verified SAT solver" returns scattered lemmas at
  distances 0.30-0.42, because the corpora hold single facts and definitions. Every record
  carries its entry's title, abstract and date: a third corpus of entries, embedding title and
  abstract (about 1,000 documents, minutes to build), would answer such questions, and a
  combined search could offer entries next to facts.

- [ ] **Search from a goal.** Agents mostly look at a subgoal, not at prose. A tool argument
  with theory, line and subgoal could take the goal from PIDE as the query. Measure first how
  goal text retrieves (it is notation, see above), with and without query expansion, which
  could turn a goal into prose.

- [ ] **Collapse restatements that differ in their terminal proof.** `collapse` merges hits with
  the same `Text_Preparation.statement`, which drops a structured `proof` but keeps `by ...`,
  so `lemma a: "P" by simp` and `lemma b: "P" by auto` stay apart. Cutting at the first proof
  command needs Isabelle's outer syntax tokens rather than a regular expression; it would also
  sharpen the duplicate analysis and the informalization input, whose goldens and prompts
  change with it.

- [ ] **Expand queries with a smaller local model.** `llamacpp_query_server` runs the server's
  query model (Gemma 4 26B-A4B, QAT `UD-Q4_K_XL`) locally with the server's prompts and
  sampling, disabled in the default `etc/search.json`. It is a 14 GB download and kept about
  5.4 GB resident on an M2 Pro with 32 GB, which 16 GB machines may not spare. It reproduces
  the server's expansions closely (eight queries: same first hit, 9 or 10 of the same top 10;
  see the run's README) at about 4 s per query on the M2 Pro.

  Expansion pays off: the paper's run with Phi-3.5-mini at Q4_0 (3.8B) raised Hit@10 from
  0.635 to 0.773 and MRR from 0.439 to 0.546 for about 1.4 s per query; on the current corpus,
  original plus expanded query (`UR`) with Gemma 4 reached Hit@10 0.863 and MRR 0.613 against
  0.811 and 0.577 without (September index against November's, so only roughly comparable).
  Most of the gain is on noisy queries.

  Still to measure on the laptop with the `UR` strategy: the whole benchmark, and one or two
  models of 1 to 4B parameters (e.g. Qwen3-1.7B and 4B, a small Gemma 4), with their latency on
  CPU and Metal. An expansion generates some 100 to 200 tokens, so a 4B model probably needs
  10 to 20 s on an Intel CPU without a GPU; cap `max_tokens` accordingly. The expand prompt
  asks for a paraphrase plus an Isabelle statement; a small model may do better with only the
  paraphrase. A smaller model is then only another `hf_repo` in the configuration.

  Cheapest for Intel laptops: train the small query encoder (see "Release the index on
  GitHub") to map a raw query to the teacher's embedding of query plus expansion, so expansion
  costs nothing per query.

## Informalization

- [ ] **Fix the truncation issues.** Both ends of the description step cut text. Done means:
  every build reports both kinds of cut, and an index of the AFP has none that a user can see
  in a description.
  - Output: descriptions cut off at `max_tokens` (512) on every attempt are kept and listed as
    `truncated_descriptions` in the manifest: 13 theorem descriptions in the build of
    2026-11-06, one definition in that of 2026-11-05. Find out why these run long (a long
    statement, or a model that loops), then raise `max_tokens` for them, retry with a prompt
    that asks for brevity, or cut at the last complete sentence.
  - Input: the describe prompt (`Corpus_Build`, `isabelle/src/corpus.scala`) and the duplicate
    judge (`isabelle/src/duplicates.scala`) both take
    `truncate(strip_proof(src), theorem_max_length)`, a plain cut at a number of characters,
    silent and possibly mid-string. A real run described "the theorem ends abruptly with
    `and \"`", which is the good case; the bad case is a description of a statement that was
    never there. This is worse than the output cut, and it also affects the duplicate judge,
    which shares the excerpt on purpose.

  The cap is 3000 characters (since a measurement of locales: 7.2% of locale blocks in the AFP
  exceed 1000 characters, median 219, p99 2619, max 6311, against 0.8-2% for the other
  definitional commands; at 3000 every category is below 1%). Over the 302,873 theorem
  documents (median statement 149 characters, 95th percentile 461, longest 19,960):

  | cap | statements still cut |
  | --- | --- |
  | 1000 | 2,513 (0.83%) |
  | 2000 | 621 (0.21%) |
  | 3000 (current) | 288 (0.10%) |
  | 5000 | 113 (0.04%) |

  3000 removes 88% of the cut theorem statements for roughly an hour of a multi-day build.
  Still open, roughly in order of effort:
  - Raise the cap further only after checking `n_ctx` at the server's `/props`: input tokens
    are cheap (prefill is faster than generation), but long prompts compete for the per-slot
    context, which `--parallel` divides among the slots.
  - Cut at a boundary (the last complete line, or the last balanced `"..."`), so the model
    always receives a syntactically whole prefix.
  - Derive the budget from the model's context window and `max_tokens` instead of a constant.
  - Count and report every cut statement, as truncated completions are.

  Raising the cap does not regenerate descriptions made from a cut statement: the checksum
  covers `src`, not the excerpt, so those entries have to be deleted by hand to be redone.

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
  A lemma or definition inside a `locale`/`context` block is its own document, but its block is
  just the statement: the locale's `fixes` and `assumes` are in the locale's header block. So
  `lemma add_commute: "a + b = b + a"` is described without the assumptions of, say, a
  commutative-group locale. Search and duplicate detection work either way; the description is
  less precise than the source allows.

  Sketch: the entity kname names the enclosing locale (e.g.
  `Abstract_First_Goedel.Goedel_Form.goedel_first_theEasyHalf` is *theory.locale.name*), and the
  locale's header is a corpus document since `locale` is in `solr_query_definitions`, so the
  header can be looked up by kname and prepended to the describe prompt ("this statement is
  made inside the following locale: ..."). Costs: every locale-interior description changes,
  so do it with the next deliberate corpus rebuild; and the duplicate judge shares the
  excerpt, so either it sees the locale context too (probably better: cross-locale near-twins
  are judged with their hypotheses) or excerpt and describe input differ, which breaks the
  "judge sees what was informalized" invariant on purpose and must be documented.

  (Decided: facts generated by `interpretation` are no documents; the locale-level original
  represents them, which keeps thousands of instantiation copies out of results and the
  duplicate report.)

- [ ] **Decide whether package-generated lemmas and constants should be searchable.** The corpus
  is built from FindFacts source blocks, which exist only where a command stands in the theory
  text. Facts generated by definitional packages (`list.induct`, `t.simps`, `t.cases`,
  discriminators and selectors of `datatype`, `.intros` of `inductive`, `.psimps` of
  `function`, ...) are therefore no documents: not searchable, not informalized, invisible to
  the duplicate detection. Only the generating command's block is in the corpus; for
  definitions its Solr `consts`/`typs` fields list the generated constants, on which the
  synthetic ground truth keys.

  Left out on purpose (command facet over the full index, 2026-09-04, 817,769 blocks): alias
  bundles that restate facts (`lemmas` 14,345, `named_theorems` 755, `lemmas_with` 136), which
  would be near-duplicates by construction; auxiliary lemmas whose block is a directive
  (`inductive_cases` 918, `termination` 693, `arity_theorem` 180, `inductive_simps` 147,
  `equivariance` 109, `sepref_thm` 105); entry-specific generator macros with no readable
  statement (`derive` 259, `mk_VLambda` 204, `synthesize` 145, `mk_ide` 143); SPARK proof
  obligations (`spark_vc` 54); and the Isabelle/DOF starred variants (`lemma*` 2,
  `definition*` 1), which would need wildcard-escaped Solr queries for a handful of documents.

  Decide before implementing: "induction principle for rose trees" is well served by the
  `datatype rose_tree` block, and generated facts are numerous, mechanical and near-identical,
  so embedding hundreds of thousands of them would flood results and the duplicate report
  (IsaFinder indexes them per entity and needed dedicated agent skills for datatype and
  intro/elim rules plus an infrastructure filter). Adding them needs an entity-level export
  from Isabelle/ML (the theory's fact space, as `find_theorems` sees it) next to FindFacts,
  which the Isabelle component could host. A cheaper middle ground: mention the generated
  fact names in the generating block's description.

  An agent's view (2026-11-06): a hit's names already list the generated facts
  (`deriv.induct`, introduction rules), so they are reachable in two steps; missing is
  matching their statements, e.g. `rtrancl_into_rtrancl` lost to AFP restatements of itself.
  Worth indexing, tagged as generated so that a search can leave them out: introduction rules
  of inductive definitions, induction rules of `function`, and the map/set/rel facts of
  datatypes (`list.set_map`); not `.cases`, `.exhaust`, `.inject`, `.distinct`, `.split`,
  `.size` or `.simps`.

## Build ergonomics

- [ ] **Let the Isabelle component build an index without progress output.**
  `isabelle isasearch_index` prints a `Prepared N of TOTAL ...` line after every batch of 32
  documents, plus a description sample, and appends both to its log. Reading back from the
  stores (about 825 documents per second on the server) that is some 25 lines per second over
  the 515,000 documents of the AFP, and in tmux the output seemed to cost noticeable time.
  Automatic builds need none of it.

  Sketch: a `-q` option without the per-batch progress and samples, keeping the phase lines
  (`Index ...`, `FindFacts index is current ...`), warnings, errors and each corpus' summary;
  truncated and undescribed documents are in the manifest anyway. Measure first against a run
  with its output sent to `/dev/null`. If the terminal is the cost, printing at most every few
  seconds may suffice without an option, or the per-batch lines could need the existing `-v`.

## Indexing

- [ ] **Incremental FindFacts indexing.** Every index build starts from zero because
  `find_facts_index` hardcodes `clean = true` when it opens the Solr database
  (`src/Tools/Find_Facts/src/find_facts.scala`), with no usage or system option around it,
  still in Isabelle2026. The incremental machinery exists in the same file and runs on every
  build: `delete_session` clears a session before it is re-indexed and `update_theory` diffs
  per-theory block domains; only the CLI entry point wipes first. Fix: an upstream patch that
  makes `clean` an option (index the named sessions into the existing database;
  `delete_session` handles replacement; dropped sessions need explicit removal). Until then,
  `Corpus_Build.export_sources` re-indexes all sessions whenever its state file
  (`find_facts.json`: the FindFacts database and the build ID of every session) changes, so a
  single rebuilt session costs a full FindFacts index.
