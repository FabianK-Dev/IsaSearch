# Isabelle2026: session builds can lose the PIDE exports of all theories

## Summary

A batch build occasionally stores a session without the PIDE exports of its
theories (`PIDE/document_id`, `PIDE/files`, `PIDE/markup`, `PIDE/messages`, …),
although the build succeeds and all other exports (`theory/…`, `document/…`) are
present. It affects all theories of the session at once. Tools that read theories
through `Build.read_theory` then see nothing: Find_Facts reports
`No snapshot for theory …` for every theory and indexes nothing from the session.

The cause appears to be a race in `Session.nodes_status_buffer`
(`src/Pure/PIDE/session.scala`). If its thread wakes between the prover exit and
`Session.stop`, it discards the finished theories instead of posting them, and the
`finished_theories` consumer of `Build_Job` never writes their exports.

## Environment

- Isabelle2026 release (`isabelle version -i`: `096842708b28`), Linux x86_64
  (Debian 13), 8 cores, 47 GB RAM.
- AFP 2026, Mercurial clone at tag `Isabelle2026` (`bc4afd781172`).
- One `Build.build` of all AFP sessions and the HOL sessions of the distribution,
  `max_jobs = 2`, `timeout_scale = 3`, run over about 33 hours.

## Observation

After the build, 67 of the 1,168 session databases (`heaps/*/log/*.db`) contain
exports but not a single `PIDE/document_id`. In every affected session no theory
has it. Among them are `HOL-Algebra`, `Core_DOM`, `Flyspeck-Tame`, `Isabelle_DOF`,
`Complex_Bounded_Operators`, `Optics` and `Szpilrajn`. The other 1,101 databases
have PIDE exports for all theories. Nothing in the ROOT options sets the affected
sessions apart, and their builds are spread evenly over the whole run (between
1 and 9 per hour). About 6 % of the session builds are affected.

For example, in `Core_DOM.db` every theory has only its `theory/…` and
`document/…` exports, e.g. `Core_DOM.Node_removeChild`:

```
document/latex  theory/axioms  theory/consts  theory/other/fact
theory/other_kinds  theory/parents  theory/thms
```

Find_Facts (`find_facts_index`) then warns for each theory:

```
### No snapshot for theory Core_DOM.Document_getElementById
### No snapshot for theory Core_DOM.Node_insertBefore
### No snapshot for theory Core_DOM.Node_removeChild
### No snapshot for theory Core_DOM.Core_DOM_Tests
```

`Build.read_theory` (`src/Pure/Build/build.scala`) returns `None` because
`theory_context.document_id()` finds no `PIDE/document_id`
(`Export.DOCUMENT_ID`, `src/Pure/Build/export.scala`).

## Where the exports are lost

`Build_Job` writes the PIDE exports in its consumer of
`session.finished_theories` (`src/Pure/Build/build_job.scala`, line 380 ff.), one
`Session.Finished_Theory` per theory. These events come from
`Session.nodes_status_buffer` (`src/Pure/PIDE/session.scala`, line 395 ff.):

1. When the prover exits, `handle_exit` (line 661) calls
   `nodes_status_buffer.finish_theory(snapshot)` for every theory. This only adds
   the snapshot to `State.finished_theories`; `State.finished` is still `false`.
2. The buffer thread runs `main()` every `nodes_status_delay`
   (`editor_output_delay`, 0.1 s by default). Each run takes the state and
   resets it in one step (line 432):

   ```scala
   val current = state.change_result(st => (st, st.reset))
   ```

   `State.reset` (line 409) clears `finished_theories`. The taken theories are
   posted only if the state was already finished (line 467):

   ```scala
   if (current.finished) {
     for (thy_snapshot <- current.finished_theories) {
       finished_theories.post(...)
     }
   }
   ```

3. `State.finished` is set only by `nodes_status_buffer.shutdown()` (line 483),
   from `Session.stop()` (line 929, `nodes_status_buffer.shutdown()` at line 941).
   `Build_Job` calls `session.stop()` only after `process.await_shutdown()` and
   cancelling the timeout (`build_job.scala`, lines 491–500).

If the buffer thread runs `main()` after step 1 but before step 3, it takes all
finished theories with `finished = false`, resets them and posts nothing. The
final run after `shutdown()` then has nothing left to post, so no theory of the
session gets its PIDE exports. Whether this happens depends on the timing of the
prover exit, the 0.1 s polling and the shutdown in `Build_Job`, which fits the
observed rate and the absence of any pattern among the affected sessions.

This is derived from the code and the state of the build databases; I have not
forced the interleaving to reproduce it deterministically.

## Suggested fix

Keep finished theories in the buffer until they can be posted, e.g. reset them
only together with the final state:

```scala
val current =
  state.change_result(st => (st, if (st.finished) st.reset else st.copy(changed_nodes = Set.empty)))
```

Alternatively, post `finished_theories` whenever they are present, without
waiting for `finished`: `finish_theory` is only called from `handle_exit`, so the
theories are complete at that point.

## Detecting affected sessions

A build database is affected if some theory has exports but no
`PIDE/document_id`, e.g.:

```sql
SELECT theory_name FROM isabelle_exports
GROUP BY theory_name
HAVING SUM(name = 'PIDE/document_id') = 0;
```

In Scala, with `Export.read_entry_names(db, session)`, group the entries by
theory and look for one without `Export.DOCUMENT_ID`.

## Workaround

Building an affected session again restores its exports (unless the race hits
again), but it produces a new heap, so all descendants are rebuilt as well. In
the build above that means 144 sessions: the 67 affected sessions and 77
descendants (`HOL-Algebra` alone has 49). IsaSearch now checks every built
session for its PIDE exports, builds incomplete sessions again (up to three builds
in all), and leaves out those that remain incomplete.
