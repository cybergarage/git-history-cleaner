# Changelog

## 1.1.0 — 2026-10-29

- Make push --remote optional: CLI > flat TOML remote > original source policy.
  Capture branch pushRemote/pushDefault/remote and pushurl/url at clean time,
  refuse ambiguity/self-targets, and preserve the exact branch/lease scope.
- Reread saved config context for push; default rebase to the published destination.

- Add strict flat repository-local TOML with explicit CLI precedence.
- Analyze to stdout and remove the saved-plan compatibility workflow.
- Add plan-free isolated clean with completed audit evidence and explicit leased publication.
- Document the complete publish, existing-clone migration and artifact lifecycle.
- Breaking: remove analyze-legacy, standalone rewrite, saved-plan consumers,
  --work-dir/--plan/--include-backup and all git-compress migration-notice scripts.
  Keep verify, push, rebase and cleanup for current clean audit/result records;
  old saved-plan runs are rejected before modification.
- Add run-free marker discovery: exclusive clean reservation, unique-result
  verification/publication/migration, and confirmed scope-wide cleanup.
- Keep --run as an optional expert scope anchor without ambiguity bypass; refuse
  old markerless results and unsafe/foreign/corrupt operation artifacts.
- Preserve added work, backups and reflog/object recovery data during cleanup.

## 1.0.0 — 2026-10-27

First general-purpose packaged release, under the name `git-history-cleaner`.

- Add analyze, rewrite, verify, push, rebase and cleanup subcommands.
- Separate remote publication from analysis and isolated history rewriting.
- Preserve the complete current tree and protect unselected historical paths.
- Support literal paths, deleted directories, extensions, exclusions and sizes.
- Handle Unicode, spaces, tabs and newlines in Git paths.
- Add immutable cleanup plans, run records, machine-readable results and errors.
- Keep full mirror backups and retain local rebase backup branches.
- Require explicit backup deletion and validated run directories for cleanup.
- Make preload pushes optional and support histories shorter than a chunk.
- Remove hardcoded organizations, repository URLs and default branch names.
- Package for Python 3.10+, macOS and Linux with MIT licensing.
- Add local Git integration tests and build/publish workflows.

### Breaking changes

The pre-release git-compress command family is replaced by the unified CLI.
See [migration notes](docs/migration.md).
