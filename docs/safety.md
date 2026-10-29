# Safety and recovery

## Scope and guarantees

Version 1.0.0 rewrites one branch in an isolated working clone. Clean leaves the source unchanged and does not create a mirror backup. Legacy analysis retains an unchanged full mirror. The selected branch's HEAD tree must match exactly
before a result is accepted, including file modes, symlinks and gitlinks. Blob
protection spans all files in that tree, not just selected extensions.

Global stripping conservatively protects blobs that occur at unselected paths
anywhere in the selected history. An absent selected path can be removed while
identical content remains at another path. These rules trade maximum size
reduction for preservation. Inspect analyze stdout and completed audit evidence for scope (legacy runs use `plan.json`).

Tags and other branches are not published or rewritten by this workflow; legacy mirror snapshots retain them. They may keep removed blobs reachable. Old clones, reflogs, stashes,
pull-request refs and host retention policies can also retain old objects. This
tool does not promise server storage savings or secret erasure. LFS pointers are
ordinary Git blobs; LFS objects are not deleted. Submodule repositories are not
rewritten. Symlink contents are blobs and are covered by the same selection rules.

Commit IDs change when their contents or ancestry change. Signed commits lose
their signatures during filtering; tags on the remote continue pointing to old
history. Historical source builds may no longer be reproducible. Coordinate the
rewrite with collaborators and branch-protection administrators before pushing.

## Snapshot and run records

A clean run contains `run.json`, `rewritten/`, completed `audit.json` and
`verification.json`. It contains no plan or mirror; keep your source clone yourself
if rollback is needed. Audit integrity is checked before later verify/push calls.
The audit is written only after successful in-memory verification and cannot be
used as a rewrite input. A failed run retains its diagnostic state and partial clone.

A legacy run contains:

- `backup.git/`: full mirror of advertised source refs and objects at snapshot time.
- `plan.json`: branch, immutable selection rules, IDs and source refs.
- `run.json`: identity, absolute location, plan checksum, state and push details.
- `rewritten/`: single-branch working clone, created by rewrite.
- `verification.json`: successful verification results.
- Internal filter input files, where a rewrite was needed.

Local uncommitted files and untracked files are not backed up. Never put unrelated
personal files in the run directory. Do not use manifests obtained from untrusted
sources, edit manifests, or run simultaneous commands against one run. Repository
URLs are recorded in plans and errors; use credential helpers or SSH rather than
embedding access tokens in URLs.

## Failure before push

The source is unchanged. Keep the failed run for diagnosis and inspect the error
in `run.json` where available. Create a new run to retry a failed rewrite. Do not
repair the backup in place. A failed analysis may have an incomplete backup;
only an analyzed run has a completed snapshot and plan.

## Push failure or interruption

A changed destination tip is rejected by the old-OID lease. Do not replace it
with an unconditional force push. Fetch and analyze the new branch instead.

Preload mode records temporary refs and their expected object IDs. A failed
cleanup leaves those records. Compare remote IDs with the recorded values and
delete only matching temporary refs using explicit leases. After an interruption,
first inspect the destination branch: a push may have succeeded before its state
was recorded. Preserve the run and resolve that situation manually; do not blindly
rerun or edit `run.json` to bypass validation.

## Roll back a published branch

For a clean run, use your retained original clone as the recovery source in place of `backup.git` below. First stop concurrent updates and inspect the remote tip. If it still equals the
run's `new_head`, restore only the affected branch from the mirror:

```sh
git -C /path/to/run/backup.git push \
  --force-with-lease=refs/heads/BRANCH:NEW_HEAD \
  DESTINATION OLD_HEAD:refs/heads/BRANCH
```

Replace the uppercase placeholders with the exact values in the plan and run.
If new commits have arrived, coordinate recovery rather than overwriting them.
Do not use `push --mirror`: that would affect unrelated branches and tags.

## Existing clones

Prefer a fresh clone. For local commits based on the pre-rewrite tip, the `rebase`
command fetches the new tip, checks its identity and preserves a backup branch.
For conflicts, inspect the working tree and use `git rebase --continue` or
`git rebase --abort`. The retained backup keeps old objects reachable until you
explicitly remove it after checking the migrated work. Avoid merging old history
back into the rewritten branch, which can reintroduce removed objects.
