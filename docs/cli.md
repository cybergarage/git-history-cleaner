# CLI reference

`git-history-cleaner --version` prints the package version. Each subcommand has
`--help`, `--json`/`--no-json`, and mutually exclusive `--config PATH`/`--no-config`. JSON mode emits one result object; operational errors go to stderr (JSON `{"error": "..."}` in JSON mode) with exit code 1. Argument errors use argparse's stderr and
exit code 2. Success is 0. Git progress is captured; analysis of a large history
can take time.

## analyze

Prints current selection to stdout without creating run/plan/report artifacts.
Remote inspection uses an automatically removed temporary clone. `--json` changes
format only; shell redirection is explicit. Configuration and selectors are shared
with `clean`; see the [README](../README.md#shared-configuration).

| Option | Meaning |
| --- | --- |
| `--repo SOURCE` | Local repository path or clone URL; default `.` |
| `--branch NAME` | Source branch; default source HEAD branch |
| `--path PATH` | Repeatable literal file/directory; default whole repository when other selectors are present |
| `--exclude PATH` | Repeatable literal file/directory excluded from selection |
| `--ext EXT[,EXT...]` | Repeatable case-insensitive filename extensions; no default extension list |
| `--preset documents` | Add doc, docx, jpeg, jpg, pdf, png extensions |
| `--min-bytes N` | Inclusive blob size threshold in bytes; default 0 |

Explicit extensions and the preset are combined. Paths do not follow renames;
select both old and new locations when appropriate. Absolute paths, `..`, and
`.git` components are rejected in selectors. The repository source itself can
be absolute. Empty repositories, detached default HEAD without `--branch`, and
shallow histories are unsupported.

Analysis scans each unique historical tree: memory and time grow with the number
of distinct trees and path/blob associations. There is no hosted size benchmark.

## clean

Accepts the same selection options as analyze, without `--plan` or `--work-dir`.
Freezes source commit and normalized selection in memory, rechecks the source,
clones only the selected branch without tags into a managed `.git-history-cleaner-*`
workspace under the invocation directory, filters and verifies it. Prints absolute
`run` and `repository` paths, `old_head`, `new_head`, and verification status.
No plan is serialized or consumed. The source is unchanged; no push is automatic.
Completed `audit.json` and its digest retain verification/publication evidence,
not an input for another rewrite. Failed runs retain state/error and partial
artifacts for diagnosis; retry starts a new run. Filter inputs are removed after use.

## analyze-legacy

Explicit compatibility export for existing `rewrite --plan` users. Accepts the
analyze options plus optional `--work-dir NEW_DIR`; omission creates a managed
workspace. Saves a full mirror, immutable plan and manifest. Existing saved plans
and downstream commands remain supported; plain analyze no longer exports plans.

## rewrite

`rewrite --plan RUN/plan.json` clones the snapshot's selected branch with no tags,
rewrites it, and automatically verifies it. It never pushes. Editing the plan or
backup invalidates the run; create another analysis to change selection. A
failed or completed rewrite cannot be repeated in the same run.

The plan checksum detects accidental edits; manifests are trusted local run
records, not authenticated data from arbitrary third parties.

## verify

`verify --run RUN` checks the recorded rewritten HEAD, a clean worktree, complete
HEAD tree equality, unreachable stripped blobs and absent removed paths within
the selected branch, and Git object integrity. Results are saved to
`verification.json`. This does not verify host-side object garbage collection,
unselected refs, or that removed data is absent from every other clone.

## push

`push --run RUN --remote DESTINATION [--yes] [--push-chunk-size N]`

DESTINATION is a clone URL or local bare repository path, not a remote nickname.
It is deliberately mandatory, even when the analysis source was remote. This
command re-verifies the run and requires the destination branch to match the
original commit before any preload. Its final push has an explicit old-OID lease.
Other branches and tags are not pushed.

The default chunk size is 0 (disabled). A positive value preloads checkpoints
through temporary branches and then deletes them with leases. It handles
histories shorter than N. Commit-count splitting does not guarantee a maximum
pack size and may trigger hosting automation or encounter branch policy limits.
Remaining temporary refs are recorded in `run.json`; resolve those before
retrying or deleting the run.

Non-interactive push requires `--yes`. For machine use, combine `--yes --json`.

## rebase

`rebase --run RUN [--repo PATH] [--remote origin] [--branch NAME]`

Replays local work after the old tip onto the verified new tip; the run must have
been pushed. The local branch uses explicit CLI/config branch, otherwise the recorded branch. It must contain
the old tip and have a clean worktree. A branch with no new commits is moved to
the new base. The fetched branch must exactly match the run's new tip; later
remote commits need manual inspection. Backup branches are always retained.
Use `git rebase --continue` or `git rebase --abort` after a conflict.

## cleanup

`cleanup --run RUN [--include-backup] [--yes]`

Deletes one recognized run at its recorded absolute location and its cleaned repository/reports. Legacy mirror deletion additionally requires `--include-backup`. It requires a confirmation or `--yes`; an unresolved preload
prevents deletion. Moving a run requires manual management because the recorded
root no longer matches. No wildcard or prefix-based deletion is performed.
