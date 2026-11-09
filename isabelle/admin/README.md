# Server automation

[`update`](update) is the maintainer script that keeps a released index current. It works
for any index: the run directories under [`runs`](../runs) hold build configurations, this
directory the automation.

## Updates and releases

`update -c CONFIG -i NAME` keeps the index `NAME`, built with `CONFIG`, current with the
registered AFP, analyses new entries for duplicates, and releases every new state on GitHub
(option `isasearch_releases`):

1. It pulls the registered AFP (`AFP_BASE`, a clean Mercurial clone) and updates it to the
   newest changeset. If the changesets since the last build touch `thys` or `metadata`, it
   builds the index again and prunes the older generations; otherwise it only records the
   revision.
2. After a build, it runs `isasearch_duplicates -k all` on the entries that the changesets
   added (each adds `metadata/entries/ENTRY.toml`), against the new index and with the LLM
   judge of `CONFIG`. The report goes to
   `$ISASEARCH_HOME_USER/update/NAME/duplicates/REVISION`. Entries whose sessions failed to
   build are listed as not in the index.
3. It exports the new generation (`isasearch_export`), compresses it with zstd, splits it into
   parts below GitHub's 2 GiB limit, and publishes them as release
   `index-NAME-DATE-afp-REVISION` with the manifest, `SHA256SUMS` and notes, unless the data
   equals that of the last release. The duplicate analysis of the revision is part of the
   release: the reports `duplicates-afp-REVISION.json`, `_near-exact.md` and `_possible.md`,
   and a table per entry in the notes. The release names the component commit that built it
   and `CONFIG` in it, so the checkout must be pushed and clean and track `CONFIG`.

`isasearch_import` relies on this layout: it matches `REVISION` against the user's AFP and
installs the parts.

Runs never overlap, also for different indexes. A failed build is retried after 24 hours or
when the AFP moves again; a failed release is retried by the next run and its draft deleted. A
failed duplicate analysis does not hold up the release: it is retried after 24 hours or with
the next build, and a later report is attached to the release of its revision, replacing an
earlier one. State lives in `$ISASEARCH_HOME_USER/update/NAME` (`built` and `released` are AFP
revisions, `duplicates_pending` the entries still to analyse); runs that do something log to
`$ISASEARCH_HOME_USER/logs/update-*.log`.

- `-f` builds even without new changesets.
- `-e ENTRY` (repeatable) analyses `ENTRY` as well, together with the entries already
  analysed for the revision, e.g. to analyse an entry again.
- `-o DIR` is a dry run: it writes the release's assets and notes, and a duplicate analysis
  that `-e` or pending entries call for, to `DIR` instead of publishing them. It needs no
  token and leaves the release and analysis state as it is, so a later run publishes nothing
  of it. A build that it makes is real, though.

On the server, cron runs it hourly for the run
[`isabelle2026-gemma4`](../runs/isabelle2026-gemma4/README.md). Errors before a run's log
starts (e.g. a failed `hg pull`) go to `update-errors.log`:

```
PATH=/home/adm-mgrgh/.local/bin:/usr/local/bin:/usr/bin:/bin
17 * * * * /home/adm-mgrgh/IsaSearch-component/isabelle/admin/update -c /home/adm-mgrgh/IsaSearch-component/isabelle/runs/isabelle2026-gemma4/plain.json -i plain > /dev/null 2>> /home/adm-mgrgh/.isabelle/Isabelle2026/isasearch/logs/update-errors.log
```

## Server setup

On a Linux machine with access to the model servers of the configuration:

1. Install Isabelle2026 with `isabelle` on the cron `PATH`, and `hg`, `git`, `python3`,
   `zstd`, `curl` and GNU coreutils (`flock`, `split`, `sha256sum`).
2. Clone the AFP (see the [component README](../README.md#provenance)) and this repository,
   and register both: `isabelle components -u AFP` and
   `isabelle components -u REPOSITORY/isabelle`.
3. In `$ISABELLE_HOME_USER/etc/settings`, raise the JVM limits:
   `ISABELLE_TOOL_JAVA_OPTIONS="-Djava.awt.headless=true -Xms2g -Xmx24g -Xss128m"`.
4. Put the model servers' key where the configuration expects it (e.g.
   `$ISASEARCH_HOME_USER/api_key`) and a GitHub token in `$ISASEARCH_HOME_USER/github_token`
   (both `chmod 600`). The repository belongs to another account, which fine-grained tokens
   cannot reach, so it is a classic token with the `public_repo` scope of an account with push
   access. Without it, `update` builds and skips the release.
5. Run the first build by hand (see the run's README), or copy the stores `llm_cache` and
   `embeddings` from `$ISASEARCH_HOME_USER` of the old server to skip describing everything
   again.
6. Install the cron job above.
