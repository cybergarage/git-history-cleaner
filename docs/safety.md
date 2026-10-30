# Safety and recovery

## Scope and guarantees

Clean rewrites one branch in an isolated working clone. It leaves the source
unchanged and does not create a mirror backup. The selected branch's HEAD tree must match exactly
before a result is accepted, including file modes, symlinks and gitlinks. Blob
protection spans all files in that tree, not just selected extensions.

Global stripping conservatively protects blobs that occur at unselected paths
anywhere in the selected history. An absent selected path can be removed while
identical content remains at another path. These rules trade maximum size
reduction for preservation. Inspect analyze stdout and completed audit evidence for scope.

Tags and other branches are not published or rewritten by this workflow. They may keep removed blobs reachable. Old clones, reflogs, stashes,
pull-request refs and host retention policies can also retain old objects. This
tool does not promise server storage savings or secret erasure. LFS pointers are
ordinary Git blobs; LFS objects are not deleted. Submodule repositories are not
rewritten. Symlink contents are blobs and are covered by the same selection rules.

Commit IDs change when their contents or ancestry change. Signed commits lose
their signatures during filtering; tags on the remote continue pointing to old
history. Historical source builds may no longer be reproducible. Coordinate the
rewrite with collaborators and branch-protection administrators before pushing.

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

## Clean run records

An operation marker reserves a result in its invocation scope. It contains only
ownership/schema/identity/location metadata. It is not a plan. Directory locks
exclude concurrent tool operations; a reserved or uncertain marker blocks clean.

A clean result contains `run.json`, `rewritten/`, completed `audit.json` and
`verification.json`. It contains no plan or mirror; keep your source clone yourself
if rollback is needed. Audit integrity is checked before later verify/push calls.
The audit is written only after successful in-memory verification and cannot be
used as a rewrite input. A failed run retains its diagnostic state and partial clone.

Local uncommitted files and untracked files are not backed up. Never put unrelated
personal files in the run directory. Do not use manifests obtained from untrusted
sources, edit manifests, or run simultaneous commands against one run. Repository
URLs are recorded in audit records and errors; use credential helpers or SSH rather than
embedding access tokens in URLs.

## Failure before push

The source is unchanged. Keep the failed run for diagnosis and inspect the error
in `run.json` where available. Retry with a new clean invocation. Standalone
analyze retains no run artifacts. Failed clean artifacts can be explicitly
removed with scope-wide cleanup after inspection when ownership is proven;
corrupt or uncertain metadata is never automatically removed. No old saved-plan
or markerless result is adopted.

## Push failure or interruption

A changed destination tip is rejected by the old-OID lease. Do not replace it
with an unconditional force push. Inspect the current branch and run clean again against the intended source.

Uploads are planned against a conservative 1.5 GiB raw-object budget; this is
an estimate, not an exact measurement of the network pack. Oversized individual
commits fail before upload. Progress is streamed and captured in failure errors.

Checkpoint refs and their expected IDs remain recorded on failure. Rerun `push`
against the same destination to resume: confirmed checkpoints are reused, missing
ones can be uploaded, and concurrently changed refs are refused. Final main-branch
publication still uses the original old-OID lease. Temporary refs are deleted with
leases only after publication succeeds; failed deletions remain recorded.

A lost response is checked against the destination ref. If the branch already
matches the verified rewritten HEAD, push records success without republishing
main. Preserve the run; do not edit `run.json` to bypass validation. Rebase and
local artifact cleanup remain separate explicit commands.

## Roll back a published branch

First stop concurrent updates and inspect the remote tip. If it still equals
the run's `new_head`, use your retained original clone to restore only the
affected branch:

```sh
git -C /path/to/retained-original-clone push \
  --force-with-lease=refs/heads/BRANCH:NEW_HEAD \
  DESTINATION OLD_HEAD:refs/heads/BRANCH
```

Replace the uppercase placeholders with the exact values reported by clean and retained in its audit/run records.
If new commits have arrived, coordinate recovery rather than overwriting them.
Do not use `push --mirror`: that would affect unrelated branches and tags.

## Existing clones

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
# Migrate the current source clone (configuration targets this local clone)
git-history-cleaner rebase
# Or, from the same operation scope, migrate another existing clone
git-history-cleaner rebase --no-config --repo /path/to/existing-clone --remote origin
```

`--no-config` is not required for the current-clone example. It is used in the
other-clone example to ignore settings that may target a different repository or
branch. See [rebase configuration](configuration.md#rebase-configuration).
Do not cleanup first: rebase requires the operation's recorded push state.

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

## Cleanup ownership and user work

Discovery is limited to the invocation's private Git directory (working tree) or
current directory (outside Git), never a search for the latest run. The UUID marker
and result manifest must agree on schema, identity, owner and exact direct-child
paths. A filename prefix alone conveys no deletion authority. Symlink/nonregular
metadata, traversal, mismatched ownership and unknown files cause refusal. Optional
expert --run chooses a recorded scope; it cannot bypass uniqueness checks.

Cleanup validates all candidates before asking, prints paths/count, and revalidates
after confirmation before deletion. Cancellation or failed validation deletes
nothing. It preserves sources and recovery branches in other clones. Local,
untracked/ignored work, extra refs and changed Git metadata/reflog/object-store
inventory in a result cause refusal, protecting work even after commit/reset.
Object inventory uses file identity/size/change times instead of rereading entire
packs; arbitrary hostile concurrent filesystem writes are outside the local
trusted-user model. All cooperating tool operations share the scope lock. A crash
mid-deletion can leave partial artifacts; inspect uncertain remaining data manually.

## Destination policy

The original source's push remote/URL is captured at clean time; the isolated
clone's origin is never trusted as a publication default. Push resolves explicit
CLI, then live flat TOML remote, then the saved source policy. Ambiguous/missing
policies and self/local-working-tree targets fail instead of choosing another
remote. Config context is retained and reread deliberately; missing prior config
fails. Review the resolved destination shown before confirmation. Every path
retains the recorded branch, old-tip check and explicit lease. Default rebase
fetches the successfully recorded destination and checks its exact new tip.

On repeated verification, an identical owned verification report and matching
repository metadata fingerprint allow reuse of the historical inventory. The
fingerprint covers object file identity, size, nanosecond modification/change
times, and non-index Git metadata contents. HEAD, worktree, current tree and
`git fsck --full` are always rechecked. Missing/changed evidence takes the full
historical scan; this also works with intact v1.1.0 results.
