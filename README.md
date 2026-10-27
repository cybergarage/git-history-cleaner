# git-history-cleaner

[![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![CI](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Remove obsolete file versions from Git history while preserving the current
branch's complete file tree. Version 1.0.0 generalizes the original
`cybergarage-pub-cleaner` scripts into an installable Python CLI.

The tool snapshots the repository, produces a reviewable plan, rewrites an
isolated clone using [git-filter-repo](https://github.com/newren/git-filter-repo),
and verifies the result before an explicit push. It never rewrites your source
working copy.

## Requirements and installation

- Python 3.10 or later and Git 2.36 or later on PATH.
- macOS or Linux. Native Windows is not supported in 1.0.0.
- Enough free disk space for a full mirror backup and a working clone.

Install from [PyPI](https://pypi.org/project/git-history-cleaner/) with:

```sh
pipx install git-history-cleaner==1.0.0
git-history-cleaner --version
```

To install from a source checkout:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

`git-filter-repo` is installed as a Python dependency. The CLI can also be
invoked as `git history-cleaner` when its executable is on PATH.

## Quick start

From a local repository, analyze old PDFs and images under `assets`:

```sh
git-history-cleaner analyze --repo . --path assets \
  --ext pdf,png,jpg --work-dir ../cleanup-run
```

Read `../cleanup-run/plan.json`. Then rewrite and verify the isolated snapshot:

```sh
git-history-cleaner rewrite --plan ../cleanup-run/plan.json
git-history-cleaner verify --run ../cleanup-run
```

The rewritten working copy is `../cleanup-run/rewritten`. Your original
repository and the mirror at `../cleanup-run/backup.git` retain their old history.
Neither `analyze` nor `rewrite` pushes anything.

After reviewing the result and coordinating with collaborators, explicitly
choose the destination:

```sh
git-history-cleaner push --run ../cleanup-run \
  --remote git@github.com:example/project.git
```

The destination branch must still match the analyzed commit. Push uses an
explicit `--force-with-lease` and asks for confirmation; `--yes` enables batch
operation. Only the analyzed branch is pushed. Protected branches may reject it.

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

## What is preserved

- Every blob used anywhere in the selected branch's current tree, regardless of
  filename extension or selected directory, is protected from blob stripping.
- Blobs used by any unselected historical path are protected from global
  stripping. This conservative policy may retain some old selected versions.
- Selected historical paths absent from the current tree are removed when all
  their recorded blob versions meet the size threshold. Their content can remain
  at other paths.
- Verification requires the complete HEAD tree ID to remain identical, checks
  selected removals throughout branch history, and runs `git fsck --full`.
- Other remote branches and tags are not changed. They may retain old objects.

Historical commits can lose files; empty commits and merge topology are retained.
Commit IDs and signatures can change. This is history rewriting, not ordinary
`git gc`. It is not a complete secret-erasure tool.

`selected_blob_bytes` is a sum of uncompressed blob sizes selected for global
stripping, not an estimate of pack-file or server storage savings. It excludes
additional effects of removing historical paths.

## Existing clones and backups

A fresh clone is the simplest way to adopt the rewritten branch. To replay local
commits made after the old branch tip:

```sh
git-history-cleaner rebase --repo /path/to/existing-clone --run ../cleanup-run
```

This requires a pushed run, a clean working tree, and the rewritten remote tip.
It retains a backup branch and attempts to preserve merge structure. Resolve
conflicts manually, or use `git rebase --abort`.

Delete a run only after verification and collaborator migration:

```sh
git-history-cleaner cleanup --run ../cleanup-run --include-backup
```

This deletes the entire run **including the mirror backup**. It validates the
run manifest and refuses unexpected top-level files or symlinks. It does not
scan directories by a filename prefix. A backup can retain substantial disk space
until you deliberately remove it.

## Documentation

- [CLI reference](docs/cli.md)
- [Safety, limitations and recovery](docs/safety.md)
- [Migration from git-compress](docs/migration.md)
- [Building and publishing 1.0.0](docs/releasing.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python -m build
python -m twine check --strict dist/*
```

Tests create temporary local repositories and bare remotes; they never push to a
hosted service. The GitHub workflows test macOS/Linux and build the distribution.
Publishing is a separate, manually dispatched workflow using PyPI Trusted
Publishing; see the release guide for the required account configuration.

MIT licensed. See [LICENSE](LICENSE).
