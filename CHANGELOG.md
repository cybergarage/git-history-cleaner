# Changelog

## Unreleased

- Add strict flat repository-local TOML with explicit CLI precedence.
- Analyze to stdout; export old plans explicitly with analyze-legacy.
- Add plan-free isolated clean with completed audit evidence and explicit leased publication.
- Document the complete publish, existing-clone migration and artifact lifecycle.


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
