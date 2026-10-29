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

## Clean run records

A clean run contains `run.json`, `rewritten/`, completed `audit.json` and
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
removed with cleanup after inspection; no old saved-plan run is accepted.

## Push failure or interruption

A changed destination tip is rejected by the old-OID lease. Do not replace it
with an unconditional force push. Inspect the current branch and run clean again against the intended source.

Preload mode records temporary refs and their expected object IDs. A failed
cleanup leaves those records. Compare remote IDs with the recorded values and
delete only matching temporary refs using explicit leases. After an interruption,
first inspect the destination branch: a push may have succeeded before its state
was recorded. Preserve the run and resolve that situation manually; do not blindly
rerun or edit `run.json` to bypass validation.

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

Prefer a fresh clone. For local commits based on the pre-rewrite tip, the `rebase`
command fetches the new tip, checks its identity and preserves a backup branch.
For conflicts, inspect the working tree and use `git rebase --continue` or
`git rebase --abort`. The retained backup keeps old objects reachable until you
explicitly remove it after checking the migrated work. Avoid merging old history
back into the rewritten branch, which can reintroduce removed objects.
