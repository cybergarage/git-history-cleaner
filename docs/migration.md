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
# Explicit publication of the exact result printed above
git-history-cleaner push --run /ABSOLUTE/PRINTED/RUN --remote DESTINATION
```

Do not pass an analysis report as an execution input. Clean creates no plan and
never automatically publishes or rewrites the source working copy. It retains a
verified result at the printed location until explicit cleanup.

Existing saved-plan runs are intentionally unsupported by the new verify, push,
rebase and cleanup commands. They are rejected before any repository update or
deletion; no automatic conversion or removal is attempted. Keep any original
sources, old run artifacts and unpublished work you still need under your own
control, and create a new clean result from the intended current source. Existing
plan-free clean results with their audit records remain supported at their
recorded locations.

`verify`, `push`, `rebase` and `cleanup` are maintained for current clean results.
Verify is optional because clean verifies and push re-verifies. Rebase checks the
published new tip before replaying local commits and retains a recovery branch;
cleanup deletes only the recognized result after confirmation. Neither a prior
analyze nor a chain of maintenance commands is required to finish clean.

Configuration stays flat and declarative, with explicit CLI values taking
precedence. No action or command sections are accepted. See the
[complete README workflow](../README.md#complete-workflow) for lease-protected
publication, fresh-clone migration, controlled rebase and artifact cleanup.
