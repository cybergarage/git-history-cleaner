# CLI reference

`git-history-cleaner --version` prints the package version. Each subcommand has
`--help`, `--json`/`--no-json`, and mutually exclusive `--config PATH`/`--no-config`. JSON mode emits one result object; operational errors go to stderr (JSON `{"error": "..."}` in JSON mode) with exit code 1. Argument errors use argparse's stderr and
exit code 2. Success is 0. Git progress is captured; analysis of a large history
can take time.

## analyze

Prints current selection to stdout without creating run/plan/report artifacts.
Remote inspection uses an automatically removed temporary clone. `--json` changes
format only; shell redirection is explicit. Configuration and selectors are shared
with `clean`; see the [configuration reference](configuration.md).

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

To save an optional JSON preview, redirect stdout explicitly. Keep the output
outside the source working tree if you will rebase it later:

```sh
git-history-cleaner analyze --repo . --path assets --ext pdf,png,jpg --json > /tmp/analysis.json
```

## Selection examples

Paths are literal, repository-relative file or directory names, not globs.
Repeated paths are combined. Filters for path, extension and size are intersected;
exclusions take precedence. Deleted directories can be selected.

```sh
# Entire repository, old blobs of at least 10 MiB
git-history-cleaner analyze --repo . --path . --min-bytes 10485760

# Multiple paths with an excluded subtree
git-history-cleaner analyze --repo . --path assets --path archived \
  --exclude assets/vendor --ext pdf

# The original document/image extensions, explicitly selected
git-history-cleaner analyze --repo . --preset documents

# Remote source, explicit branch
git-history-cleaner analyze --repo https://github.com/example/project.git \
  --branch release --path assets --ext zip --json
```

With no path, extensions and size thresholds apply to the whole repository.
An entirely unfiltered analysis requires explicit `--path .`.
The default branch is the source's HEAD branch, not a hardcoded `main`.
Local sources include committed history only; uncommitted files and stash are
not part of the branch being rewritten.

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

`push [--remote DESTINATION] [--yes] [--push-chunk-size N] [--max-push-bytes N]`

See [push destination resolution](#push-destination-resolution) below for
configuration, saved source policy and lease checks.

Uploads use a conservative raw-object budget of 1.5 GiB by default. The estimate
includes object/framing overhead and does not rely on existing pack deltas; it is
not a measurement of bytes sent on the wire. `--max-push-bytes N` sets a positive
budget. All checkpoints are planned before upload. A single commit whose new
reachable objects exceed the budget is rejected without changing history. A
positive `--push-chunk-size N` adds a commit-count bound; 0 leaves byte planning
in charge. Temporary branches can trigger hosting automation or branch policy.

Rerun push to resume the same result, including v1.1.0 `push-failed` results.
Checkpoints are retained on failure and recorded in `run.json`. Resume checks
recorded refs and their destination, refuses concurrent changes, skips confirmed
uploads, and removes owned temporary refs with leases after final success.
If a response is lost, push checks the remote ref before deciding failure. An
already published rewritten HEAD is recognized without another main-branch push.
Git progress is included in captured failure diagnostics. No clean/rebase is
performed by resume.

Non-interactive push requires `--yes`. For machine use, combine `--yes --json`.

## Push destination resolution

`push` itself is always explicit; `--remote` is optional. Resolve one concrete
URL or local bare path in this order:

1. Explicit `push --remote URL_OR_PATH` (relative paths use invocation cwd).
2. Flat TOML `remote = "URL_OR_PATH"` (relative paths use the config directory).
3. Original source push policy saved during clean: for a local source, target
   branch `pushRemote`, then `remote.pushDefault`, then target branch `remote`,
   otherwise its sole configured remote. Use that remote's one pushurl, or its
   one url if no pushurl exists. Original relative remote paths use the original
   repository directory. For a remote clean source, use its saved URL.

A remote value is a destination, **not** a nickname such as `origin`. Ordinary
strings are filesystem paths; use HTTP(S), SSH, Git, file URLs, or scp-style Git
addresses for URLs. Command/helper protocols are unsupported. Local targets must
be bare, must not be the original local source, and must not be inside the result.
Missing or multiple remote choices/URLs, an explicit self-target policy (`.`),
invalid values and a changed destination tip fail; nothing falls back elsewhere.
The isolated clone's origin is never used for inference.

Original Git push configuration is frozen at clean time; later source remote
changes do not retarget the result. The selected TOML path is recorded as context,
not a saved destination: push rereads it, so changing its `remote` intentionally
changes that next push destination after lease checks and confirmation. Removing
or corrupting a previously loaded config fails rather than silently retargeting.
A newly created config at the recorded automatic path can be used. Explicit
`push --config FILE` replaces this context; `--no-config` disables it. Marker
`--run` context also uses that recorded file rather than an unrelated current tree.
Selection/HEAD/audit policy remains frozen. Results made before destination
snapshot support need an explicit CLI/config destination.

Push displays the resolved destination and its origin on stderr before asking
for confirmation, including with `--yes`. It always sends only the recorded branch
with an explicit old-SHA lease; Git mirror/refspec/followTags/submodule-push
settings do not broaden the operation. No automatic push occurs during clean.
Default `rebase` fetches the recorded successful push destination, even if the
clone's origin differs. An explicit rebase `--remote NAME_OR_URL` remains an expert
override requiring the exact recorded new branch tip; flat TOML `remote` is not a
rebase remote name.

The destination branch must still equal the recorded `old_head`. Protected
branches may reject rewriting. Never substitute unconditional force, `--all`
or `--mirror` to bypass the selected-branch scope.

The equivalent raw Git operation, after verification and with exact printed
values, is:

```sh
git -C /ABSOLUTE/PRINTED/REPOSITORY push \
  --force-with-lease=refs/heads/BRANCH:OLD_HEAD \
  git@github.com:example/project.git NEW_HEAD:refs/heads/BRANCH
```

Do not push from the original source clone or assume `origin` exists in the
result. Raw Git push does not record the pushed state required by tool rebase.

## rebase

Use this before cleanup when an existing local clone will continue to be used,
even if it has no new commits. It is unnecessary for a disposable clone or when
switching to a fresh clone. See [migration examples](safety.md#existing-clones)
and [rebase configuration](configuration.md#rebase-configuration).

`rebase [--repo PATH] [--remote NAME_OR_URL] [--branch NAME]`

Replays local work after the old tip onto the verified new tip; the run must have
been pushed. By default fetch the recorded successful push destination; an
explicit --remote name/URL is an expert override that must produce the same new
tip. TOML remote applies only to push. The local branch uses explicit CLI/config branch, otherwise the recorded branch. It must contain
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

All commands use the same invocation scope: inside a Git working tree, its private
Git directory (`git rev-parse --absolute-git-dir`); otherwise the current directory.
Nested invocations share that worktree's scope; linked worktrees have separate
private scopes. `--repo` selects a source or migration target and does not redirect
operation discovery. Run following commands from the same scope, including when
migrating another clone with `rebase --repo /path/to/existing-clone`.

Clean reserves `.git-history-cleaner-operation-<UUID>.json` and creates the direct
sibling `.git-history-cleaner-result-<UUID>/`. The marker contains only ownership,
schema, identity and result-location metadata, never deletion targets or an
execution plan. A directory lock plus exclusive marker reservation prevents
concurrent tool operations. No permanent lock file is needed. Source files and
Git history remain unchanged by clean; Git-directory metadata stays untracked.

- Clean refuses any existing operation marker or leftover result in the scope,
  including failed or uncertain artifacts. Analyze remains independent and writes
  only to stdout.
- Verify, push and rebase require exactly one valid complete operation. Zero means
  run clean first; multiple operations mean ambiguity and refusal. There is no
  newest-run choice.
- An optional expert `--run /absolute/result` anchors discovery to that result's
  recorded scope. It must match the sole operation and cannot override ambiguity.
  For cleanup, it anchors the scope whose **all** operations will be considered;
  it does not restrict deletion to just one result.
- Cleanup preflights every candidate, prints the exact scope/paths/count, asks for
  confirmation, rechecks after confirmation and removes all proven owned markers
  and results. `--yes` explicitly confirms a batch invocation; cancellation deletes
  nothing. It removes no source clone, external recovery branch or unrelated file.
- Active operations cannot be cleaned. After interruption, intact reserved markers
  or owned incomplete results can be cleaned once no operation holds the lock.
  Missing/corrupt records, foreign files, unexpected content, altered result Git
  metadata/recovery objects, extra refs, local/ignored work or unresolved remote
  temporary refs cause refusal before deletion. Preserve your work yourself and
  inspect uncertain data manually; do not rename arbitrary files to match a prefix.

A crash during metadata initialization can leave incomplete/corrupt ownership
records. Those require manual inspection, not prefix-based deletion. After a push
interruption, rerun `push`: it checks the destination against the rewritten HEAD,
recognizes an already published result, and resumes recorded checkpoints.
Old markerless results are not discovered or adopted automatically; see [migration](migration.md).

## Command settings and output

All commands support `--help`, `--config PATH` / `--no-config`, and `--json` /
`--no-json`. `--version` is top-level. Selection settings apply to analyze/clean,
repo/branch also to rebase, `remote` only to push, formatting to all commands. Verify, push, rebase and
cleanup accept the optional expert `--run` scope anchor described above. It is
never needed for the ordinary workflow. Verify/rebase/cleanup are maintenance
commands; clean already completes local rewriting and verification by itself.

No normal command requires `--run`, a RUN variable, a plan, or a path handoff.
Clean prints `marker`, `repository`, `run`, `branch`, `old_head`, `new_head` and
verification status. These paths are informational; following commands discover
the unique operation automatically. You can inspect the printed repository with
`git -C /ABSOLUTE/PRINTED/REPOSITORY log --oneline -10`.

The CLI can also be invoked as `git history-cleaner` when its executable is on PATH.

On repeated verification, an identical owned verification report and matching
repository metadata fingerprint allow reuse of the historical inventory. The
fingerprint covers object file identity, size, nanosecond modification/change
times, and non-index Git metadata contents. HEAD, worktree, current tree and
`git fsck --full` are always rechecked. Missing/changed evidence takes the full
historical scan; this also works with intact v1.1.0 results.
