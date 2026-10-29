# Breaking migration to the clean workflow

The saved-plan compatibility workflow has been removed. `analyze-legacy` and
standalone `rewrite` no longer exist; `--plan`, `--work-dir` and cleanup's
`--include-backup` are no longer accepted. The old `git-compress`,
`git-compress-chk`, `git-compress-clean` and `git-compress-rebase` migration-notice
scripts have also been deleted instead of keeping obsolete command entry points.

Use the supported commands:

```sh
# Optional informational stdout preview
git-history-cleaner analyze --repo . --path assets --ext pdf,png,jpg
# Independently select, rewrite an isolated clone and verify in one invocation
git-history-cleaner clean --repo . --path assets --ext pdf,png,jpg
# Explicit publication, resolving destination from TOML or the original source
git-history-cleaner push
```

Do not pass an analysis report as an execution input. Clean creates no plan and
never automatically publishes or rewrites the source working copy. It retains a
verified result at the printed location until explicit cleanup.

Existing saved-plan runs are intentionally unsupported by the new verify, push,
rebase and cleanup commands. They are rejected before any repository update or
deletion; no automatic conversion or removal is attempted. Keep any original
sources, old run artifacts and unpublished work you still need under your own
control, and create a new clean result from the intended current source. Results from before marker ownership was introduced are not automatically
adopted or deleted, even with an expert --run selector. Inspect/manage those
artifacts yourself and create a new marked operation from the intended source.

`verify`, `push`, `rebase` and `cleanup` are maintained for current clean results.
Verify is optional because clean verifies and push re-verifies. Rebase checks the
published new tip before replaying local commits and retains a recovery branch;
cleanup deletes all proven operations in the invocation scope after confirmation. Neither a prior
analyze nor a chain of maintenance commands is required to finish clean.

Configuration stays flat and declarative, with explicit CLI values taking
precedence. No action or command sections are accepted. See the
[complete README workflow](../README.md#complete-workflow) for lease-protected
publication, fresh-clone migration, controlled rebase and artifact cleanup.

## Run-free operations

Normal verify, push, rebase and cleanup no longer require `--run`. Remain in the
same invocation scope: the private Git directory inside a working tree, otherwise
the current directory. A source/target `--repo` does not change this scope.
Clean refuses existing operation markers or leftover results. Verify/push/rebase
require exactly one valid operation; cleanup validates and confirms removal of
all proven operations. Nothing selects a newest run. Optional expert `--run`
anchors a recognized result's scope and never bypasses ambiguity; cleanup remains
scope-wide. See [marker discovery/recovery](../README.md#operation-markers-and-recovery).

## Optional push destination

Push --remote remains supported but is no longer required. Flat TOML remote is a
URL/bare path, not a command section or a rebase remote name. CLI overrides TOML,
then clean's saved original push policy supplies inference. Previously created
results without that snapshot need CLI/config remote. Push rereads its recorded
config context; a removed previously loaded file fails until explicitly replaced
or disabled with --no-config. Default rebase now follows the actual recorded push
destination, rather than assuming origin. See the README resolution rules.
