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

Accepts the same selection options as analyze. The tool manages its workspace.
Freezes source commit and normalized selection in memory, rechecks the source,
clones only the selected branch without tags into a managed `.git-history-cleaner-result-<UUID>`
workspace in the invocation scope (private Git directory or current directory), filters and verifies it. Prints absolute
`marker`, `run` and `repository` paths, branch, old/new commit IDs and verification status.
A marker reserves the operation; clean refuses existing markers or leftovers.
No plan is serialized or consumed. The source is unchanged; no push is automatic.
Completed `audit.json` and its digest retain verification/publication evidence,
not an input for another rewrite. Failed runs retain state/error and partial
artifacts for diagnosis; inspect and cleanup the existing operation before retry.
Filter inputs are removed after use.

## verify

`verify` checks the recorded rewritten HEAD, a clean worktree, complete
HEAD tree equality, unreachable stripped blobs and absent removed paths within
the selected branch, and Git object integrity. Results are saved to
`verification.json`. This does not verify host-side object garbage collection,
unselected refs, or that removed data is absent from every other clone.

## push

`push --remote DESTINATION [--yes] [--push-chunk-size N]`

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

`rebase [--repo PATH] [--remote origin] [--branch NAME]`

Replays local work after the old tip onto the verified new tip; the run must have
been pushed. The local branch uses explicit CLI/config branch, otherwise the recorded branch. It must contain
the old tip and have a clean worktree. A branch with no new commits is moved to
the new base. The fetched branch must exactly match the run's new tip; later
remote commits need manual inspection. Backup branches are always retained.
Use `git rebase --continue` or `git rebase --abort` after a conflict.

## cleanup

`cleanup [--yes]`

Preflights all operation markers/results in the invocation scope, prints a summary,
requires confirmation (or explicit `--yes`), rechecks records and deletes only
proven owned artifacts. Cancellation deletes nothing. Active operations, pending
remote temporary refs, unknown/foreign/corrupt data, symlinks, unexpected content,
changed result metadata, local/ignored work and recovery refs/objects cause refusal.
The source and external recovery branches are never deleted. Valid interrupted
reservations or orphaned owned results can be cleaned; uncertain initialization
needs manual inspection. Nothing is deleted merely for matching a prefix.

## Discovery and expert selection

Inside a working tree, discover in that worktree's private Git directory; outside,
use the current directory. No global/ancestor marker search and no latest-run guess.
`--repo` changes a source/target, not discovery. Keep following commands in the
same scope. Nested directories and linked worktrees follow Git-directory identity.

Verify, push and rebase need exactly one valid complete operation; zero, multiple,
foreign or incomplete operations fail. Cleanup considers all candidates. Marker
`.git-history-cleaner-operation-<UUID>.json` records ownership/schema/location;
sibling `.git-history-cleaner-result-<UUID>` holds the result, never a plan.
Directory locking excludes simultaneous tool operations and marker reservation is
exclusive. Interrupted/corrupted reservations block another clean.

These four commands accept optional expert `--run /absolute/result`, which anchors
scope selection to that recognized result. It cannot bypass multiple-operation
ambiguity. Cleanup still considers all operations in the anchored scope. Old
markerless/saved-plan runs are not automatically adopted or accepted by this
selector. See [migration](migration.md).
