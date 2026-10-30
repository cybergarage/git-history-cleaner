# Configuration

The configuration file is a local, flat TOML file named `.git-history-cleaner`.
Its location controls how it is discovered; its `repo` value controls which
repository is cleaned. These are separate choices.

## Local and remote sources

Both sources use the same configuration format:

| Setting | Local source | Remote source |
| --- | --- | --- |
| `repo` | `"."` or another local path | `"git@github.com:example/project.git"` |
| `branch` | Branch to rewrite | Branch to rewrite |
| `path`, `ext`, etc. | Select within the local source | Select within the remote source |

A relative configured `repo` is resolved against the configuration file's
directory. A relative CLI `--repo` is resolved against the invocation directory.
The `remote` setting, when provided, selects the **push destination**, not the
source; see [push destination resolution](cli.md#push-destination-resolution).

## Configuration discovery

For analyze/clean and maintenance commands other than push:

1. `--no-config` disables loading.
2. `--config FILE` loads that exact local file.
3. Otherwise, inspect the local Git working-tree root selected by explicit
   `--repo`, or by the current directory if `--repo` is absent.

Read the file once, then apply its settings. Discovery does not restart after
reading a configured `repo`, and never reads configuration from a fetched
remote repository. In particular:

| Invocation | Configuration behavior |
| --- | --- |
| `clean` inside a local Git tree | Read that tree's root configuration, even if it specifies a remote `repo` |
| `clean --repo /path/to/clone` | Discover configuration at that clone's working-tree root |
| `clean --repo git@github.com:example/project.git` | No automatic configuration discovery, even when invoked inside another Git tree |
| `clean --config .git-history-cleaner` outside Git | Read the explicitly named local file and use its `repo` |
| `clean` outside Git, with a config file in the current directory | The file is not automatically discovered; use `--config` |

Push is the exception: it rereads the configuration path recorded during clean,
including an explicitly selected file outside Git. `push --config FILE` replaces
that context; `push --no-config` disables it. See
[push destination resolution](cli.md#push-destination-resolution).

Configuration discovery and operation discovery are also separate. Changing
`repo` does not move the operation marker. Keep subsequent commands in the same
[operation scope](cli.md#discovery-and-expert-selection).

## Settings and precedence

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

## Rebase configuration

Rebase accepts configured `repo` and `branch` for its **local migration target**,
plus `json` for output. It does not apply deletion selectors or TOML `remote`.
Without repo/branch settings, it uses the current repository and the branch
recorded by clean.

For a configuration with `repo = "."` and the intended branch, use:

```sh
git-history-cleaner rebase
```

`--no-config` is optional. Use it when you deliberately want to ignore configured
repo/branch settings and migrate the current clone. When a configuration's
`repo` is a remote URL, do not use that URL as a rebase target; specify an existing
local clone, from the same operation scope:

```sh
git-history-cleaner rebase --no-config --repo /path/to/existing-clone
```

Explicit `--repo` and `--branch` can also override individual configured values.
Rebase defaults to the successfully recorded push destination, regardless of
TOML `remote`. Complete all required migrations before cleanup removes the
operation records.
