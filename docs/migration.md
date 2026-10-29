# Migration from git-compress

1.0.0 is the first packaged release and deliberately changes the pre-release CLI.

| Old command | New workflow |
| --- | --- |
| `git-compress REPO DIR` | `clean --repo SOURCE --path DIR` |
| Automatic push / `--no-push` | No automatic push; use `push --run RUN --remote URL` explicitly |
| `--target-ext` / `--target-exts` | `analyze --ext` |
| Default document extensions | Explicit `--preset documents` |
| `--org cybergarage` | Explicit repository URL or local path |
| `--confirm` / no-op `--yes` | Push and cleanup confirm by default; `--yes` skips the prompt |
| `git-compress-chk` | `verify --run RUN` with nonzero exit on failed checks |
| `git-compress-clean` | `cleanup --run RUN --include-backup` |
| `git-compress-rebase OLD_BASE` | `rebase --run RUN --repo EXISTING_CLONE` |

Old script filenames remain as migration notices that exit with status 2 and do
nothing. They are not installed as package entry points. They do not silently
translate old invocations into destructive new operations.

Existing `git-compress-*` directories have no new-format manifest and are not
accepted by cleanup, verify or rebase. Keep their backups and reports; manage them
manually using the old recorded commit IDs. New runs use an explicit directory or
a `.git-history-cleaner-*` default. Rebase backups are now retained by default.

## Migrating the saved-plan workflow

Plain `analyze` now prints only to stdout. To keep explicitly exporting an old-style
plan, use `analyze-legacy --repo SOURCE --path DIR --work-dir NEW_DIR`, then
`rewrite --plan NEW_DIR/plan.json`. Existing saved plans/runs remain compatible.
For new work use `clean` directly; do not pass an analysis report as a plan.
No config action sections are accepted: use the flat shared schema in the README.
