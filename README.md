# git-history-cleaner

[![Version 1.1.0](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![CI](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Remove obsolete file versions from Git history while preserving the current
branch's complete file tree. Version 1.0.0 generalizes the original
`cybergarage-pub-cleaner` scripts into an installable Python CLI.

`analyze` previews targets on stdout. `clean` selects, rewrites an isolated clone
using [git-filter-repo](https://github.com/newren/git-filter-repo), and verifies it
in one invocation. It preserves your source working copy and never pushes automatically.
Version 1.1.0 removes saved-plan compatibility and the old script entry points;
see [migration](docs/migration.md) before upgrading from 1.0.0.

## Requirements and installation

- Python 3.10 or later and Git 2.36 or later on PATH.
- macOS or Linux. Native Windows is not supported in 1.1.0.
- Enough free disk space for an isolated full-history working clone.

Install from [PyPI](https://pypi.org/project/git-history-cleaner/) with:

```sh
pipx install git-history-cleaner==1.1.0
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

Install this source checkout first. In a local working clone:

```sh
git clone git@github.com:example/project.git project-cleaning
cd project-cleaning
# Optional preview: stdout only; no marker, report or plan is saved
git-history-cleaner analyze --repo . --path assets --ext pdf,png,jpg
git-history-cleaner analyze --repo . --path assets --ext pdf,png,jpg --json > analysis.json
# Independently select current targets, rewrite an isolated clone and verify
git-history-cleaner clean --repo . --path assets --ext pdf,png,jpg
# Optional recheck; push also re-verifies automatically
git-history-cleaner verify
# Discover the original push destination and confirm; clean never publishes
git-history-cleaner push
# Or explicitly override the destination
# git-history-cleaner push --remote git@github.com:example/project.git
```

No normal command requires `--run`, a RUN variable, a plan, or a path handoff.
Clean prints `marker`, `repository`, `run`, `branch`, `old_head`, `new_head` and
verification status. These paths are informational; following commands discover
the unique operation automatically. You can inspect the printed repository with
`git -C /ABSOLUTE/PRINTED/REPOSITORY log --oneline -10`.

The destination branch must still equal the recorded `old_head`. Push confirms,
re-verifies and uses an explicit expected-old-SHA lease. For unattended operation,
supply `--yes` on that invocation. Only the selected branch is published; other
branches and tags may retain old history. Protected branches may reject rewriting.
Never substitute unconditional force, `--all` or `--mirror` to bypass scope.

The equivalent raw Git operation, after verification and with exact printed
values, is:

```sh
git -C /ABSOLUTE/PRINTED/REPOSITORY push \
  --force-with-lease=refs/heads/BRANCH:OLD_HEAD \
  git@github.com:example/project.git NEW_HEAD:refs/heads/BRANCH
```

Do not push from the original source clone or assume `origin` exists in the
result. Raw Git push does not record the pushed state required by tool rebase.

For a remote source, start in an ordinary directory outside any Git working tree:

```sh
mkdir project-cleaning
cd project-cleaning
git-history-cleaner analyze --repo https://github.com/example/project.git \
  --branch main --path assets --ext pdf,png,jpg
git-history-cleaner clean --repo https://github.com/example/project.git \
  --branch main --path assets --ext pdf,png,jpg
git-history-cleaner push
git-history-cleaner cleanup
```

Remote sources never supply configuration automatically. Use SSH or credential
helpers; do not embed credentials in source/destination URLs.

## Push destination resolution

`push` itself is always explicit; `--remote` is optional. Resolve one concrete
URL or local bare path in this order:

1. Explicit `push --remote URL_OR_PATH` (relative paths use invocation cwd).
2. Flat TOML `remote = "URL_OR_PATH"` (relative paths use the config directory).
3. Original source push policy saved during clean: for a local source, target
   branch `pushRemote`, then `remote.pushDefault`, then target branch `remote`,
   otherwise its sole configured remote. Use that remote's one pushurl, or its
   one url if no pushurl exists. For a remote clean source, use its saved URL.

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

## Operation markers and recovery

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
interruption, inspect the destination before any retry: it may have updated before
the local pushed state was recorded. Old markerless results are not discovered or
adopted automatically; see [migration](docs/migration.md).

## Shared configuration

Create `.git-history-cleaner` at your working-tree root (a regular TOML file):

```toml
schema_version = 1
repo = "."
remote = "git@github.com:example/project.git"
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
run/plan paths, rebase remote names, cleanup scope, hooks or environment
interpolation are accepted. Unknown keys, malformed TOML, wrong types, unsupported
schema, negative sizes and symlink/nonregular config files fail before work begins.
Configuration never authorizes a push or deletion.

## Command list

| Command | Purpose |
| --- | --- |
| `analyze [selection options]` | Informational stdout preview; no operation artifacts |
| `clean [selection options]` | Reserve an operation, select, isolated rewrite and verify |
| `verify` | Recheck the unique operation |
| `push [--remote URL_OR_PATH] [--yes] [--push-chunk-size N]` | Resolve destination, confirm and publish with a lease |
| `rebase [--repo EXISTING_CLONE] [--remote NAME_OR_URL] [--branch NAME]` | Safely migrate commits after a tool-recorded push |
| `cleanup [--yes]` | Confirmed cleanup of all proven operations in the scope |

All commands support `--help`, `--config PATH` / `--no-config`, and `--json` /
`--no-json`. `--version` is top-level. Selection settings apply to analyze/clean,
repo/branch also to rebase, `remote` only to push, formatting to all commands. Verify, push, rebase and
cleanup accept the optional expert `--run` scope anchor described above. It is
never needed for the ordinary workflow. Verify/rebase/cleanup are maintenance
commands; clean already completes local rewriting and verification by itself.
See [CLI reference](docs/cli.md).

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

For controlled migration of commits based on the recorded old tip, publish with
the tool's push, then remain in the operation scope and run:

```sh
# Migrate the current source clone from the successfully published destination
git-history-cleaner rebase --no-config
# Or, from the same operation scope, migrate another existing clone
git-history-cleaner rebase --no-config --repo /path/to/existing-clone --remote origin
```

The clone must have a clean working tree and contain the old tip. Its remote tip
must still equal the cleaned new tip. Rebase retains a recovery branch and replays
local commits (zero commits also works). For conflicts use `git rebase --continue`
or `git rebase --abort`. Divergence or later remote commits require inspection.
The recovery branch retains old objects; remove it yourself only after checking
the migrated work. Never merge it back into the cleaned branch.

After publication and migration, clean all associated operation artifacts:

```sh
git-history-cleaner cleanup
# Explicitly confirmed unattended cleanup
git-history-cleaner cleanup --yes
```

Cleanup summarizes all proven artifacts and asks for confirmation. It never
removes the source or recovery branches in existing clones. Do not put personal
files or new commits in the isolated result; cleanup refuses detected changes,
including additional object/reflog recovery data, untracked and ignored files.
Keep your original work yourself if rollback is needed. You may remove a disposable
source clone yourself after checking that your work is preserved; the cleaner
never deletes it. Inside a Git working tree, marker and result artifacts live in
its private Git directory and are removed by cleanup.

## Documentation

- [CLI reference](docs/cli.md)
- [Safety, limitations and recovery](docs/safety.md)
- [Breaking migration notes](docs/migration.md)
- [Building and publishing 1.1.0](docs/releasing.md)
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
