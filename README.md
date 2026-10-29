# git-history-cleaner

[![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![CI](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Remove obsolete file versions from Git history while preserving the current
branch's complete file tree. Version 1.0.0 generalizes the original
`cybergarage-pub-cleaner` scripts into an installable Python CLI.

`analyze` previews targets on stdout. `clean` selects, rewrites an isolated clone
using [git-filter-repo](https://github.com/newren/git-filter-repo), and verifies it
in one invocation. It preserves your source working copy and never pushes automatically.
The new commands below describe this source checkout; the published 1.0.0 release
uses the legacy plan workflow.

## Requirements and installation

- Python 3.10 or later and Git 2.36 or later on PATH.
- macOS or Linux. Native Windows is not supported in 1.0.0.
- Enough free disk space for an isolated full-history working clone (plus a mirror for legacy runs).

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

## Complete workflow

Install this source checkout first. In a disposable working clone of your project:

```sh
git clone git@github.com:example/project.git project-cleaning
cd project-cleaning
# Optional preview: stdout only, no report/plan/run files
git-history-cleaner analyze --repo . --path assets --ext pdf,png,jpg
git-history-cleaner analyze --repo . --path assets --ext pdf,png,jpg --json > analysis.json
# Independently select current targets, rewrite and verify; no prior analyze needed
git-history-cleaner clean --repo . --path assets --ext pdf,png,jpg
```

Clean prints `verified`, `branch`, `old_head`, `new_head`, `run` and `repository`. For
example, the exact absolute `run` might be `/work/project-cleaning/.git-history-cleaner-ab123`
and `repository` its `rewritten` child. **Use the actual paths printed by your
invocation** in the commands below. There is no latest-run lookup. You need no
RUN variable, plan file, work directory option, or intermediate commands to clean.
Publishing still requires `push --run` with that exact printed run path and an
explicit `--remote` destination. Clean itself requires neither. A separate verify
invocation is optional because push re-verifies automatically.
The output remains at that path until you explicitly remove it. Do not move it
while using the tool's verify/push/cleanup commands.

Review the result, then explicitly publish it:

```sh
git -C /work/project-cleaning/.git-history-cleaner-ab123/rewritten log --oneline -10
git-history-cleaner verify --run /work/project-cleaning/.git-history-cleaner-ab123
git-history-cleaner push --run /work/project-cleaning/.git-history-cleaner-ab123 \
  --remote git@github.com:example/project.git
# Optional: independently inspect the published branch tip
git ls-remote git@github.com:example/project.git refs/heads/main
```

`push` re-verifies and asks for confirmation. For unattended execution, supply
`--yes` explicitly. The destination branch must still equal `old_head`; its
update uses an explicit `--force-with-lease=refs/heads/BRANCH:OLD_HEAD`. Concurrent
updates are rejected. Only the selected branch is published: other branches and
tags may retain old history. Branch protection may reject the update; coordinate
with collaborators and administrators. Never substitute `--force`, `--all`, or
`--mirror` to bypass these limits.

For users who deliberately prefer raw Git, this is the equivalent branch-only
publication **from the cleaned repository**, after verification. Replace all
uppercase placeholders with exact values reported by clean; do not use the
original source clone or assume `origin` exists (filter-repo may remove it).

```sh
git -C /ABSOLUTE/PRINTED/REPOSITORY push \
  --force-with-lease=refs/heads/BRANCH:OLD_HEAD \
  git@github.com:example/project.git NEW_HEAD:refs/heads/BRANCH
```

Raw `git push` does not record the tool's pushed state; use the tool's `push`
when you intend to use its `rebase` command later.

A remote source works without an initial manual clone, and never loads a
configuration file from downloaded history:

```sh
git-history-cleaner analyze --repo https://github.com/example/project.git \
  --branch main --path assets --ext pdf,png,jpg
git-history-cleaner clean --repo https://github.com/example/project.git \
  --branch main --path assets --ext pdf,png,jpg
```

Use SSH or credential helpers; do not embed credentials in source/destination URLs.

## Shared configuration

Create `.git-history-cleaner` at your working-tree root (a regular TOML file):

```toml
schema_version = 1
repo = "."
branch = "main"
path = ["assets", "archive"]
exclude = ["assets/vendor"]
ext = ["pdf", "png"]
min_bytes = 1048576
# preset = "documents"
json = false
```

Then invoke the action explicitly:

```sh
git-history-cleaner analyze
git-history-cleaner clean
# CLI lists replace configured lists; preset extensions still combine with ext
git-history-cleaner analyze --path assets --ext jpg --min-bytes 0 --no-json
git-history-cleaner clean --config /path/to/settings.toml
git-history-cleaner analyze --no-config --repo . --path assets --ext pdf
```

Precedence is explicit CLI > flat TOML > defaults. Repeated CLI list options
combine within the CLI layer. `--json` / `--no-json` override formatting; JSON
analysis still goes to stdout. `preset = "documents"` adds doc/docx/jpeg/jpg/pdf/png
to `ext`; the commented example is inactive. Defaults are repo `.`, source HEAD
branch, no exclusions/extensions/preset, min_bytes 0 and json false. Empty lists
retain these selector semantics; at least one positive selector is required.

Discovery checks only the selected local Git working-tree root, including nested
invocations and linked worktrees. An explicit local `--repo` selects that root;
otherwise the current tree is used. No home/global search, ancestor merging,
recursive discovery through configured repo, or remote/bare automatic config.
Explicit `--config` is relative to the invocation directory; configured filesystem
`repo` paths are relative to the config file. Selectors always refer to the source
repository. `--no-config` disables discovery; an explicit missing config is an error.

Only the keys shown above are supported. No command sections, actions, `yes`,
run/plan paths, push destinations, rebase remotes, cleanup scope, hooks or environment
interpolation are accepted. Unknown keys, malformed TOML, wrong types, unsupported
schema, negative sizes and symlink/nonregular config files fail before work begins.
Configuration never authorizes a push or deletion.

## Command list

| Command | Purpose and required controls |
| --- | --- |
| `analyze [selection options]` | Informational stdout preview, no saved plan |
| `clean [selection options]` | Select, isolated rewrite and verification in one invocation |
| `analyze-legacy [selection options] [--work-dir NEW_DIR]` | Explicit legacy snapshot/plan export |
| `rewrite --plan /absolute/run/plan.json` | Rewrite an existing legacy analyzed run |
| `verify --run /absolute/run` | Recheck a completed clean or legacy run |
| `push --run /absolute/run --remote URL [--yes] [--push-chunk-size N]` | Publish one verified branch with a lease |
| `rebase --run /absolute/run --repo EXISTING_CLONE [--remote origin] [--branch NAME]` | Migrate local commits after a tool-recorded push; creates a backup branch |
| `cleanup --run /absolute/run [--include-backup] [--yes]` | Explicitly delete one recognized run; legacy mirror requires --include-backup |

All commands support `--help`, `--config PATH` / `--no-config`, and `--json` /
`--no-json`. `--version` is a top-level option. Shared selection applies to
analyze/clean/analyze-legacy, repo/branch also to rebase, formatting to all commands.
Other execution controls stay on the CLI. See [CLI reference](docs/cli.md).

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

## Existing clones and artifact lifecycle

**A normal `git pull` is not a safe migration after a history rewrite.** It may
fail or merge the old ancestry back into the cleaned branch, reintroducing removed
history. First preserve your uncommitted, untracked and unpushed work yourself.
Do not delete an existing clone before checking that all your work is accounted for.

The simplest migration is a fresh clone into a new directory:

```sh
git clone git@github.com:example/project.git project-fresh
cd project-fresh
git log --oneline -10
```

For controlled migration of commits based on the recorded old tip, use the
completed run after publishing with the tool's `push`:

```sh
git-history-cleaner rebase --no-config \
  --repo /path/to/existing-clone \
  --run /work/project-cleaning/.git-history-cleaner-ab123 --remote origin
```

This requires a clean working tree, a local branch containing the old tip and a
remote branch still exactly at the cleaned new tip. It fetches, checks identity,
creates a backup branch, and rebases commits after the old tip (zero commits also
works). Conflicts require manual `git rebase --continue` or `git rebase --abort`.
Diverged histories or a remote with later commits need individual inspection.
The backup branch intentionally retains old objects; remove it yourself only
after checking the migrated work. Do not merge it back into the cleaned branch.

Keep the run until publishing and migration are complete. A clean run holds the
cleaned repository and completed verification/audit metadata, without a mirror
backup or plan. Its source clone remains unchanged. Legacy runs also retain a
mirror and plan. Never place personal files in a run directory.

```sh
# Deletes the exact clean result, with confirmation
git-history-cleaner cleanup --run /work/project-cleaning/.git-history-cleaner-ab123
# Legacy runs include a mirror, whose deletion must be explicitly selected
git-history-cleaner cleanup --run /absolute/legacy-run --include-backup
```

Cleanup refuses unexpected files, symlinks and unresolved temporary remote refs.
Once the result is published and verified and your own work is preserved, you
may remove the disposable project-cleaning clone yourself. Deleting that clone
also deletes any run nested inside it. Cleanup does not delete the source clone
or update other clones. Keep an original clone yourself if rollback is needed;
clean does not create a separate backup of your work.

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
