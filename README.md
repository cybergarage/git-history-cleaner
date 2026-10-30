# git-history-cleaner

[![Version 1.1.1](https://img.shields.io/badge/version-1.1.1-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![CI](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/cybergarage/git-history-cleaner/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://github.com/cybergarage/git-history-cleaner/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Remove obsolete file versions from Git history while preserving the selected
branch's complete current file tree. `clean` rewrites and verifies an isolated
clone using [git-filter-repo](https://github.com/newren/git-filter-repo).
It leaves the source clone unchanged and never pushes automatically.

History rewriting changes commit IDs. Coordinate with collaborators before
publishing; other branches, tags and old clones may retain the original history.

## Installation

Requires Python 3.10+, Git 2.36+, macOS or Linux, and enough disk space for an
isolated full-history clone. Native Windows is not supported in 1.1.1.

```sh
pipx install git-history-cleaner==1.1.1
git-history-cleaner --version
```

`git-filter-repo` is installed as a dependency. Source installation and development
instructions are in [Contributing](CONTRIBUTING.md).

## Complete workflow

Choose a source with `repo` in a **local** `.git-history-cleaner` TOML file.
Use `"."` for the repository containing that file, or a URL for a remote source.
Run each workflow's commands from the same working directory.

### Current repository

At your existing Git working-tree root, create `.git-history-cleaner`:

```toml
schema_version = 1
repo = "."
branch = "main"
path = ["assets"]
ext = ["pdf", "png", "jpg"]
```

Adjust the branch and selectors to your repository. Commit the configuration
before starting, and preserve any other uncommitted or untracked work so that
the working tree is clean for `rebase`.

```sh
git-history-cleaner analyze  # Optional preview; stdout only
git-history-cleaner clean    # Rewrite an isolated clone and verify
git-history-cleaner push     # Confirm and publish to the original push destination
git-history-cleaner rebase   # Migrate this local clone to the published history
# Check the migrated branch and your work before removing operation data
git-history-cleaner cleanup
```

`push` does not update your original local clone. Run `rebase` before `cleanup`
if you will keep using that clone, even when it has no unpushed commits.
Skip `rebase` only if you will stop using the old clone and use a fresh clone
instead. A normal `git pull` is not a safe migration.
Rebase retains a recovery branch; see [existing clones](docs/safety.md#existing-clones).

### Remote repository

In an ordinary directory outside any Git working tree, create a local
`.git-history-cleaner` file:

```toml
schema_version = 1
repo = "git@github.com:example/project.git"
branch = "main"
path = ["assets"]
ext = ["pdf", "png", "jpg"]
```

```sh
git-history-cleaner analyze --config .git-history-cleaner  # Optional
git-history-cleaner clean --config .git-history-cleaner
git-history-cleaner push     # Reuses the recorded config path and source URL
git-history-cleaner cleanup
```

There is no source working clone to migrate here, so this example omits
`rebase`. Any existing clones elsewhere still need migration or replacement
with fresh clones after publication.

### Configuration and command options

Automatic configuration discovery looks for `.git-history-cleaner` at a
local Git working-tree root. That local file can set `repo` to either a local
path or a remote URL. Outside a Git working tree, use `--config FILE` as above.
A configuration file inside the fetched remote repository is never adopted
automatically.

You can also supply options directly, for example:

```sh
git-history-cleaner clean --repo . --path assets --ext pdf,png,jpg
```

Explicit CLI options override configuration values. `--no-config` disables
configuration loading; it is not required for ordinary `rebase` use.
See [configuration](docs/configuration.md) for discovery rules and all settings.

## Commands

| Command | Purpose |
| --- | --- |
| `analyze` | Preview selected history on stdout |
| `clean` | Rewrite an isolated clone and verify it |
| `verify` | Optional recheck; push also verifies automatically |
| `push` | Confirm and publish the selected branch with an old-SHA lease |
| `rebase` | Migrate an existing local clone after a tool-recorded push |
| `cleanup` | Confirm and remove operation data, preserving source clones |

Push and cleanup are separate, explicit operations. Keep operation data until
any required migration is complete. Each command supports `--help`; normal
workflows do not require `--run` or a saved plan.

## Documentation

- [Configuration](docs/configuration.md): local/remote sources, discovery and precedence
- [CLI reference](docs/cli.md): options, selection examples, push destinations and operation discovery
- [Safety, limitations and recovery](docs/safety.md): preservation, existing clones, rollback and cleanup
- [Breaking migration notes](docs/migration.md): upgrading from 1.0.0
- [Building and publishing 1.1.1](docs/releasing.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

MIT licensed. See [LICENSE](LICENSE).

