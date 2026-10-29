"""Git snapshots, selection, rewriting and verified publication."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import uuid

FORMAT = "git-history-cleaner/1"
DOCUMENT_EXTS = [".doc", ".docx", ".jpeg", ".jpg", ".pdf", ".png"]


def git(repo, *args, data=None):
    env = os.environ.copy()
    # Caller Git environment must not redirect operations away from our clone.
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
        input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def text(repo, *args):
    return git(repo, *args).decode("utf-8", "surrogateescape").strip()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def literal_path(value):
    if not value or "\0" in value or value.startswith("/") or ".." in value.split("/"):
        raise ValueError("paths must be repository-relative without '..'")
    path = str(PurePosixPath(value))
    if ".git" in path.split("/"):
        raise ValueError("paths must not include .git")
    return path


def within(path, prefix):
    return prefix == "." or path == prefix or path.startswith(prefix + "/")


def selected(path, rules):
    return (any(within(path, p) for p in rules["paths"])
            and not any(within(path, p) for p in rules["exclude"])
            and (not rules["extensions"] or PurePosixPath(path).suffix.lower() in rules["extensions"]))


def tree(repo, revision):
    entries = {}
    for record in git(repo, "ls-tree", "-rz", "-r", revision).split(b"\0"):
        if record:
            meta, path = record.split(b"\t", 1)
            mode, kind, oid = meta.split()
            if kind == b"blob":
                entries[path.decode("utf-8", "surrogateescape")] = oid.decode()
    return entries


def inventory(repo, revision):
    """Read each distinct tree once; NUL framing preserves literal filenames."""
    trees = set(text(repo, "log", "--format=%T", revision).splitlines())
    paths = {}
    for tree_id in sorted(trees):
        for path, oid in tree(repo, tree_id).items():
            paths.setdefault(path, set()).add(oid)
    return paths


def selection(repo, revision, rules):
    current = tree(repo, revision)
    history = inventory(repo, revision)
    protected = set(current.values())
    outside = {oid for path, ids in history.items() if not selected(path, rules) for oid in ids}
    targets = {path: ids for path, ids in history.items() if selected(path, rules)}
    candidates = set().union(*targets.values()) if targets else set()
    sizes = {}
    if candidates:
        output = git(repo, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                     data=("\n".join(sorted(candidates)) + "\n").encode())
        sizes = {parts[0].decode(): int(parts[2]) for parts in map(bytes.split, output.splitlines())}
    eligible = {oid for oid in candidates if sizes[oid] >= rules["min_bytes"]}
    # Global blob deletion is allowed only if no unselected historical path uses it.
    strip = eligible - protected - outside
    # Removing an absent path is safe even when its content is retained elsewhere.
    deleted = sorted(path for path, ids in targets.items() if path not in current and ids <= eligible)
    return {"strip_blobs": sorted(strip), "deleted_paths": deleted,
            "protected_head_blobs": len(candidates & protected),
            "protected_outside_blobs": len(candidates & outside),
            "selected_blob_bytes": sum(sizes[oid] for oid in strip),
            "matched_paths": len(targets)}


def resolve_selection(args):
    source = args.repo
    if not source or "\0" in source:
        raise ValueError("repository must be a nonempty path or URL")
    local = Path(source).expanduser()
    if local.exists():
        source = (text(local, "rev-parse", "--show-toplevel")
                  if text(local, "rev-parse", "--is-inside-work-tree") == "true"
                  else str(local.resolve()))
    if not source or "\0" in source or source.startswith("-"):
        raise ValueError("repository must not start with '-'")
    if args.branch is not None:
        git(Path.cwd(), "check-ref-format", "refs/heads/" + args.branch)
    extensions = []
    for value in args.ext:
        for ext in value.split(","):
            ext = ext.strip().lower().lstrip(".")
            if not ext or "/" in ext or "\0" in ext:
                raise ValueError("invalid extension")
            extensions.append("." + ext)
    if args.preset:
        extensions.extend(DOCUMENT_EXTS)
    if not (args.path or extensions or args.min_bytes):
        raise ValueError("specify --path . explicitly, a path, extension, preset or size threshold")
    rules = {"paths": [literal_path(p) for p in args.path] or ["."],
             "exclude": [literal_path(p) for p in args.exclude],
             "extensions": sorted(set(extensions)), "min_bytes": args.min_bytes}
    return source, rules


def inspect_source(repo, source, branch, rules):
    if text(repo, "rev-parse", "--is-shallow-repository") == "true":
        raise ValueError("shallow history is unsupported; use a full repository")
    branch = branch or text(repo, "symbolic-ref", "--short", "HEAD")
    git(repo, "check-ref-format", "refs/heads/" + branch)
    old = text(repo, "rev-parse", "--verify", "refs/heads/" + branch + "^{commit}")
    return {"source": source, "branch": branch, "old_head": old,
            "old_tree": text(repo, "rev-parse", old + "^{tree}"),
            "rules": rules, "selection": selection(repo, old, rules)}


def clone_inspection(temporary, source, branch):
    options = ["--branch", branch] if branch is not None else []
    git(temporary, "clone", "--bare", "--single-branch", "--no-tags", "--no-local",
        *options, "--", source, "source.git")


def analyze(args):
    """Inspect locally without writes; remote inspection uses an ephemeral clone."""
    source, rules = resolve_selection(args)
    if Path(source).exists():
        policy = inspect_source(source, source, args.branch, rules)
    else:
        with tempfile.TemporaryDirectory(prefix="history-cleaner-inspect-") as temporary:
            clone_inspection(temporary, source, args.branch)
            policy = inspect_source(Path(temporary) / "source.git", source, args.branch, rules)
    return {"source": source, "branch": policy["branch"], "head": policy["old_head"],
            "rules": rules, **policy["selection"]}


def clean(args):
    """Freeze policy in memory; retain only completed verification/audit evidence."""
    source, rules = resolve_selection(args)
    # Validate source and freeze its tip before allocating a persistent workspace.
    local = Path(source).exists()
    if local:
        policy = inspect_source(source, source, args.branch, rules)
    else:
        with tempfile.TemporaryDirectory(prefix="history-cleaner-inspect-") as temporary:
            clone_inspection(temporary, source, args.branch)
            policy = inspect_source(Path(temporary) / "source.git", source, args.branch, rules)
    root = Path(tempfile.mkdtemp(prefix=".git-history-cleaner-", dir=Path.cwd())).resolve()
    manifest = {"format": FORMAT, "run_id": str(uuid.uuid4()), "root": str(root),
                "state": "rewriting", "workflow": "clean"}
    save(root / "run.json", manifest)
    try:
        repo = safe_repo(root, "rewritten")
        git(root, "clone", "--no-local", "--no-tags", "--single-branch", "--branch", policy["branch"],
            "--", source, str(repo))
        if text(repo, "rev-parse", "HEAD") != policy["old_head"]:
            raise ValueError("source branch changed during clean; retry")
        if selection(repo, policy["old_head"], rules) != policy["selection"]:
            raise ValueError("source selection changed during clean; retry")
        check_source(root, policy, args.branch is None)
        apply_selection(root, repo, policy["selection"])
        manifest["new_head"] = text(repo, "rev-parse", "HEAD")
        check_result(repo, manifest, policy)
        # This is completed-run evidence, never an input to a rewrite.
        save(root / "audit.json", policy)
        manifest.update(state="verified", audit_digest=digest(policy))
        save(root / "run.json", manifest)
        return verify(root)
    except Exception as exc:
        manifest.update(state="failed", error=str(exc))
        save(root / "run.json", manifest)
        raise RuntimeError(f"{exc} (artifacts: {root})") from exc


def check_source(root, policy, default_branch):
    """Reject selected-ref changes and default-HEAD switches before filtering."""
    source, branch = policy["source"], policy["branch"]
    ref = "refs/heads/" + branch
    if Path(source).exists():
        if text(source, "rev-parse", ref) != policy["old_head"]:
            raise ValueError("source branch changed during clean; retry")
        if default_branch:
            try:
                current = text(source, "symbolic-ref", "--short", "HEAD")
            except RuntimeError as exc:
                raise ValueError("source HEAD changed during clean; retry") from exc
            if current != branch:
                raise ValueError("source HEAD changed during clean; retry")
    else:
        advertised = text(root, "ls-remote", "--symref", "--", source, "HEAD", ref).splitlines()
        refs = {name: oid for oid, name in (line.split("\t", 1) for line in advertised)}
        if refs.get(ref) != policy["old_head"]:
            raise ValueError("source branch changed during clean; retry")
        if default_branch and refs.get("HEAD") != policy["old_head"]:
            raise ValueError("source HEAD changed during clean; retry")
        if default_branch and f"ref: {ref}\tHEAD" not in advertised:
            raise ValueError("source HEAD changed during clean; retry")


def apply_selection(root, repo, chosen):
    if chosen["deleted_paths"] or chosen["strip_blobs"]:
        ids = root / "strip-blobs.txt"
        callback_path = root / "filename-callback.py"
        ids.write_text("\n".join(chosen["strip_blobs"]) + "\n", encoding="ascii")
        removed = {p.encode("utf-8", "surrogateescape") for p in chosen["deleted_paths"]}
        callback_path.write_text(f"return None if filename in {removed!r} else filename", encoding="ascii")
        try:
            git(repo, "filter-repo", "--force", "--filename-callback", str(callback_path),
                "--strip-blobs-with-ids", str(ids), "--replace-refs", "delete-no-add",
                "--prune-empty", "never", "--prune-degenerate", "never")
        finally:
            ids.unlink(missing_ok=True)
            callback_path.unlink(missing_ok=True)


def load_run(value):
    requested = Path(value).absolute()
    if requested.is_symlink():
        raise ValueError("run directory must not be a symlink")
    root = requested.resolve()
    marker = root / "run.json"
    if marker.is_symlink():
        raise ValueError("run manifest must not be a symlink")
    manifest = json.loads(marker.read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT or manifest.get("root") != str(root):
        raise ValueError("not a recognized run directory at its recorded location")
    if manifest.get("workflow") != "clean":
        raise ValueError("unsupported saved-plan run; create a new result with clean")
    uuid.UUID(manifest["run_id"])
    return root, manifest


def load_audit(root, manifest):
    audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
    if digest(audit) != manifest.get("audit_digest"):
        raise ValueError("completed audit changed")
    return audit


def safe_repo(root, name):
    repo = root / name
    if repo.is_symlink() or repo.resolve().parent != root:
        raise ValueError("run repositories must not be symlinks")
    if name == "rewritten" and repo.exists() and (
            (repo / ".git").is_symlink() or not (repo / ".git").is_dir()):
        raise ValueError("rewritten .git must be an ordinary directory")
    return repo


def verify(value):
    root, manifest = load_run(value)
    if manifest["state"] not in {"verified", "pushed", "push-failed"}:
        raise ValueError("run has no completed clean to verify")
    audit = load_audit(root, manifest)
    repo = safe_repo(root, "rewritten")
    check_result(repo, manifest, audit)
    if manifest["state"] != "pushed":
        manifest["state"] = "verified"
    save(root / "run.json", manifest)
    result = {"run": str(root), "repository": str(repo), "verified": True, "head_tree_preserved": True,
              "branch": audit["branch"], "old_head": audit["old_head"], "new_head": manifest["new_head"],
              "scope": "selected branch only"}
    save(root / "verification.json", result)
    return result


def check_result(repo, manifest, audit):
    if text(repo, "rev-parse", "HEAD") != manifest["new_head"]:
        raise ValueError("rewritten HEAD changed")
    if text(repo, "status", "--porcelain"):
        raise ValueError("rewritten working tree is dirty")
    if text(repo, "rev-parse", "HEAD^{tree}") != audit["old_tree"]:
        raise ValueError("verification failed: HEAD tree changed")
    git(repo, "fsck", "--full")
    history = inventory(repo, "HEAD")
    all_ids = set().union(*history.values()) if history else set()
    if set(audit["selection"]["strip_blobs"]) & all_ids:
        raise ValueError("verification failed: selected blobs remain reachable")
    if set(audit["selection"]["deleted_paths"]) & set(history):
        raise ValueError("verification failed: deleted paths remain reachable")


def confirm(message, yes):
    if yes:
        return
    import sys
    if not sys.stdin.isatty() or input(message + " [y/N] ").strip().lower() != "y":
        raise ValueError("not confirmed; use --yes for non-interactive operation")


def push(value, remote, yes=False, chunk_size=0):
    verify(value)
    root, manifest = load_run(value)
    audit = load_audit(root, manifest)
    if manifest.get("temporary_refs"):
        raise ValueError("temporary refs from an earlier push remain; resolve them first")
    repo = safe_repo(root, "rewritten")
    # Resolve before git -C changes the meaning of a relative local destination.
    destination = str(Path(remote).resolve()) if Path(remote).exists() else remote
    if destination.startswith("-"):
        raise ValueError("remote must not start with '-'")
    ref = "refs/heads/" + audit["branch"]
    advertised = text(repo, "ls-remote", "--refs", destination, ref).split()
    if not advertised or advertised[0] != audit["old_head"]:
        raise ValueError("destination branch differs from recorded HEAD; run clean against the current source again")
    confirm(f"Rewrite {destination} {ref}?", yes)
    pending = []
    uploaded = {}
    manifest.update(destination=destination, temporary_refs=pending)
    save(root / "run.json", manifest)
    try:
        if chunk_size:
            commits = text(repo, "rev-list", "--topo-order", "--reverse", "HEAD").splitlines()
            checkpoints = commits[chunk_size - 1::chunk_size]
            if commits and (not checkpoints or checkpoints[-1] != commits[-1]):
                checkpoints.append(commits[-1])
            for index, oid in enumerate(checkpoints):
                temporary = f"refs/heads/git-history-cleaner-{manifest['run_id']}-{index}"
                pending.append(temporary)
                uploaded[temporary] = oid
                manifest["temporary_ref_oids"] = uploaded
                save(root / "run.json", manifest)
                git(repo, "push", f"--force-with-lease={temporary}:", destination, f"{oid}:{temporary}")
        git(repo, "push", f"--force-with-lease={ref}:{audit['old_head']}",
            destination, f"{manifest['new_head']}:{ref}")
        manifest["state"] = "pushed"
    except Exception as exc:
        manifest.update(state="push-failed", error=str(exc))
        raise
    finally:
        for temporary in pending[:]:
            try:
                # Delete only the value we uploaded, never a concurrently changed ref.
                current = text(repo, "ls-remote", "--refs", destination, temporary).split()
                if current:
                    git(repo, "push", f"--force-with-lease={temporary}:{uploaded[temporary]}", destination, ":" + temporary)
                pending.remove(temporary)
            except RuntimeError:
                pass
        save(root / "run.json", manifest)
    return {"pushed": True, "destination": destination, "temporary_refs_remaining": pending}


def cleanup(value, yes=False):
    root, manifest = load_run(value)
    if manifest.get("temporary_refs"):
        raise ValueError("temporary remote refs remain; resolve them before deleting this run")
    allowed = {"run.json", "rewritten", "strip-blobs.txt",
               "filename-callback.py", "verification.json", "audit.json"}
    if any(p.name not in allowed or p.is_symlink() for p in root.iterdir()):
        raise ValueError("run contains unexpected files or symlinks; refusing recursive deletion")
    confirm(f"Delete run and cleaned repository at {root}?", yes)
    shutil.rmtree(root)
    return {"deleted": str(root)}
