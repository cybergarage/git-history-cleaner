"""Scope-locked operation discovery. Markers locate results, never deletion plans."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid

from . import core

FORMAT = "git-history-cleaner/operation/1"
PREFIX = ".git-history-cleaner-operation-"
RESULT_PREFIX = ".git-history-cleaner-result-"


def scope():
    cwd = Path.cwd().resolve()
    try:
        if core.text(cwd, "rev-parse", "--is-inside-work-tree") == "true":
            return Path(core.text(cwd, "rev-parse", "--absolute-git-dir")).resolve()
    except RuntimeError:
        pass
    return cwd


def owned_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
        raise ValueError(f"unsafe or foreign metadata file: {path}")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        actual = os.fstat(fd)
        if (info.st_dev, info.st_ino) != (actual.st_dev, actual.st_ino):
            raise ValueError(f"metadata changed while reading: {path}")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = None
            try:
                value = json.load(stream)
            except (ValueError, UnicodeError) as exc:
                raise ValueError(f"corrupt metadata at {path}: {exc}") from exc
    finally:
        if fd is not None:
            os.close(fd)
    if not isinstance(value, dict):
        raise ValueError(f"invalid metadata object: {path}")
    return value


@contextmanager
def locked(directory):
    # Directory locks need no leftover lock file and cannot be replaced by unlinking one.
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another operation is active in this scope; wait for it to finish") from exc
        yield
    finally:
        os.close(fd)


def entries(directory):
    return sorted(directory.glob(PREFIX + "*"))


def result_entries(directory):
    return sorted(directory.glob(RESULT_PREFIX + "*"))


def assert_empty(directory):
    if entries(directory) or result_entries(directory):
        raise ValueError(f"an operation marker or result already exists in {directory}; inspect it or run cleanup")


def create(directory, manifest):
    identifier = manifest["run_id"]
    path = directory / (PREFIX + identifier + ".json")
    value = {"format": FORMAT, "id": identifier, "scope": str(directory),
             "result": RESULT_PREFIX + identifier, "owner_uid": os.getuid()}
    payload = (json.dumps(value, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        # A partial marker remains a blocking, uncertain artifact, never silently ignored.
        raise
    return path


def read_marker(path, directory):
    value = owned_file(path)
    if set(value) != {"format", "id", "scope", "result", "owner_uid"}:
        raise ValueError(f"unknown operation marker schema: {path}")
    identifier = value["id"]
    try:
        valid_id = type(identifier) is str and str(uuid.UUID(identifier)) == identifier
    except ValueError:
        valid_id = False
    if (not valid_id
            or value["format"] != FORMAT or value["scope"] != str(directory)
            or type(value["owner_uid"]) is not int or value["owner_uid"] != os.getuid()
            or path.name != PREFIX + identifier + ".json"
            or value["result"] != RESULT_PREFIX + identifier):
        raise ValueError(f"foreign or invalid operation marker: {path}")
    return value


def validate_root(root, directory, identifier):
    if root.parent != directory or root.name != RESULT_PREFIX + identifier:
        raise ValueError("result must be a direct operation-owned child of its scope")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError(f"unsafe result directory: {root}")
    manifest = owned_file(root / "run.json")
    allowed = {"format", "workflow", "root", "run_id", "operation_scope", "operation_marker", "owner_uid",
               "state", "source", "old_head", "branch", "repo_metadata", "new_head", "audit_digest", "error",
               "destination", "temporary_refs", "temporary_ref_oids"}
    if set(manifest) - allowed or any(type(manifest.get(key)) is not str for key in ("state", "source", "old_head", "branch")):
        raise ValueError("invalid or foreign result schema")
    if manifest["state"] not in {"rewriting", "verified", "pushed", "push-failed", "failed"}:
        raise ValueError("unknown result state")
    if (manifest.get("format") != core.FORMAT or manifest.get("workflow") != "clean"
            or manifest.get("root") != str(root) or manifest.get("run_id") != identifier
            or manifest.get("operation_scope") != str(directory)
            or manifest.get("operation_marker") != PREFIX + identifier + ".json"
            or type(manifest.get("owner_uid")) is not int or manifest["owner_uid"] != os.getuid()):
        raise ValueError(f"result ownership metadata does not match its marker: {root}")
    return manifest


def candidates(directory):
    records = []
    seen = set()
    for marker in entries(directory):
        value = read_marker(marker, directory)
        root = directory / value["result"]
        manifest = validate_root(root, directory, value["id"]) if root.exists() or root.is_symlink() else None
        records.append((marker, root, manifest))
        seen.add(root)
    # Incomplete initialization can leave a result without a published marker.
    for root in result_entries(directory):
        if root not in seen:
            identifier = root.name[len(RESULT_PREFIX):]
            try:
                valid_id = str(uuid.UUID(identifier)) == identifier
            except ValueError:
                valid_id = False
            if not valid_id:
                raise ValueError(f"foreign result directory: {root}")
            manifest = validate_root(root, directory, identifier)
            records.append((None, root, manifest))
    return records


def selected_scope(explicit=None):
    if explicit is None:
        return scope()
    root, manifest = core.load_run(explicit)
    recorded_scope = manifest.get("operation_scope")
    if type(recorded_scope) is not str:
        raise ValueError("explicit --run has no valid operation scope; old markerless results are unsupported")
    directory = Path(recorded_scope)
    if not directory.is_absolute() or directory != directory.resolve():
        raise ValueError("explicit --run has no valid operation scope; old markerless results are unsupported")
    validate_root(root, directory, manifest["run_id"])
    return directory


def select(directory, explicit=None):
    records = candidates(directory)
    if not records:
        raise ValueError(f"no operation found in {directory}; run clean first")
    if len(records) != 1:
        raise ValueError(f"multiple operations found in {directory}; inspect and cleanup; --run does not bypass ambiguity")
    marker, root, manifest = records[0]
    if marker is None or manifest is None:
        raise ValueError("operation initialization is incomplete; inspect it and run cleanup")
    if explicit is not None and root != Path(explicit).absolute():
        raise ValueError("explicit --run does not match the unique operation")
    return root


@contextmanager
def operation(explicit=None):
    directory = selected_scope(explicit)
    with locked(directory):
        yield select(directory, explicit)


def metadata_fingerprint(repo):
    """Detect added recovery data without rereading potentially huge object packs."""
    gitdir = repo / ".git"
    items = []
    for path in sorted(gitdir.rglob("*")):
        info = path.lstat()
        relative = path.relative_to(gitdir)
        if stat.S_ISDIR(info.st_mode):
            items.append((str(relative), "directory"))
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("unexpected symlink, hardlink or special file in clone metadata")
        elif relative == Path("index"):
            # Read-only status may refresh index stats; staged work is checked separately.
            items.append((str(relative), "index"))
        elif relative.parts[0] == "objects":
            items.append((str(relative), info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
        else:
            items.append((str(relative), hashlib.sha256(path.read_bytes()).hexdigest()))
    return core.digest(items)


def cleanup_check(record):
    marker, root, manifest = record
    if manifest is None:
        return
    if manifest.get("temporary_refs"):
        raise ValueError("temporary remote refs remain; resolve them before cleanup")
    allowed = {"run.json", "rewritten", "verification.json", "audit.json"}
    for path in root.iterdir():
        if path.name not in allowed or path.is_symlink():
            raise ValueError("result contains unexpected files or symlinks; refusing cleanup")
        if path.name == "rewritten":
            if not path.is_dir():
                raise ValueError("result repository must be a directory")
        else:
            owned_file(path)
    if (root / "audit.json").exists():
        core.load_audit(root, manifest)
    if (root / "verification.json").exists():
        report = owned_file(root / "verification.json")
        expected_report = {"run": str(root), "marker": str(root.parent / manifest["operation_marker"]),
                           "repository": str(root / "rewritten"), "verified": True, "head_tree_preserved": True,
                           "branch": manifest["branch"], "old_head": manifest["old_head"],
                           "new_head": manifest.get("new_head"), "scope": "selected branch only"}
        if report != expected_report or report.get("verified") is not True or report.get("head_tree_preserved") is not True:
            raise ValueError("verification report changed or is foreign; refusing cleanup")
    source = Path(manifest.get("source", ""))
    if source.exists() and source.resolve().is_relative_to(root):
        raise ValueError("result contains the source repository; refusing cleanup")
    repo = root / "rewritten"
    if repo.exists():
        repo = core.safe_repo(root, "rewritten")
        if core.text(repo, "status", "--porcelain", "--ignored", "--untracked-files=all"):
            raise ValueError("result has local, untracked or ignored work; preserve it yourself before cleanup")
        if manifest.get("repo_metadata") != metadata_fingerprint(repo):
            raise ValueError("result Git metadata changed or contains additional files; refusing cleanup")
        expected = manifest.get("new_head") or manifest.get("old_head")
        if core.text(repo, "rev-parse", "HEAD") != expected:
            raise ValueError("result HEAD changed or is uncertain; refusing cleanup")
        branch = manifest["branch"]
        allowed_refs = {"refs/heads/" + branch, "refs/remotes/origin/" + branch, "refs/remotes/origin/HEAD"}
        for line in core.text(repo, "for-each-ref", "--format=%(refname) %(objectname)").splitlines():
            ref, oid = line.split()
            if ref not in allowed_refs or oid != expected:
                raise ValueError("result has additional refs or backups; refusing cleanup")
        allowed_git = {"HEAD", "config", "description", "hooks", "info", "objects", "refs", "logs", "packed-refs",
                       "index", "filter-repo", "FETCH_HEAD", "ORIG_HEAD", "COMMIT_EDITMSG"}
        if any(p.name not in allowed_git for p in (repo / ".git").iterdir()):
            raise ValueError("result Git directory contains unexpected files; refusing cleanup")


def fingerprint(records):
    result = []
    for marker, root, manifest in records:
        marker_data = marker.read_bytes() if marker is not None else None
        info = root.lstat() if manifest is not None else None
        result.append((str(marker), str(root), marker_data, manifest,
                       (info.st_dev, info.st_ino) if info is not None else None))
    return result


def cleanup(explicit=None, yes=False):
    directory = selected_scope(explicit)
    with locked(directory):
        records = candidates(directory)
        if not records:
            raise ValueError(f"no operation found in {directory}; nothing to cleanup")
        if explicit is not None and Path(explicit).absolute() not in {r[1] for r in records}:
            raise ValueError("explicit --run does not match this scope")
        for record in records:
            cleanup_check(record)
        before = fingerprint(records)
        paths = [str(root) for _, root, manifest in records if manifest is not None]
        markers = [str(marker) for marker, _, _ in records if marker is not None]
        summary = f"Cleanup {len(records)} operation(s) in {directory}: " + ", ".join(paths + markers)
        print(summary, file=sys.stderr)
        core.confirm(summary + "; delete all these owned artifacts?", yes)
        current = candidates(directory)
        for record in current:
            cleanup_check(record)
        if fingerprint(current) != before:
            raise ValueError("operation artifacts changed during confirmation; refusing cleanup")
        for marker, root, manifest in current:
            if manifest is not None:
                shutil.rmtree(root)
            if marker is not None:
                marker.unlink()
        return {"deleted": paths, "markers_removed": markers}
