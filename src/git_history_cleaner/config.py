"""Strict, single-pass repository-local declarative configuration."""
from pathlib import Path
import stat

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

from . import core

KEYS = {"schema_version": int, "repo": str, "branch": str, "path": list,
        "exclude": list, "ext": list, "preset": str, "min_bytes": int, "json": bool}
SELECTION = {"repo", "branch", "path", "exclude", "ext", "preset", "min_bytes"}
DEFAULTS = dict(repo=".", branch=None, path=[], exclude=[], ext=[], preset=None, min_bytes=0, json=False)


def discover(repo):
    path = Path(repo).expanduser()
    if not path.exists():
        return None
    try:
        if core.text(path, "rev-parse", "--is-inside-work-tree") != "true":
            return None
        return Path(core.text(path, "rev-parse", "--show-toplevel")) / ".git-history-cleaner"
    except RuntimeError:
        return None


def read(path):
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError("config must be a regular file, not a symlink or directory")
    try:
        with path.open("rb") as stream:
            values = tomllib.load(stream)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"invalid TOML: {exc}") from exc
    for key, value in values.items():
        if key not in KEYS:
            if key == "yes":
                raise ValueError("config 'yes' is forbidden; confirm interactively or supply --yes")
            raise ValueError(f"unsupported config key/section: {key}; use flat shared settings only")
        if type(value) is not KEYS[key]:
            raise ValueError(f"config {key} must be {KEYS[key].__name__}")
        if isinstance(value, list) and any(type(v) is not str for v in value):
            raise ValueError(f"config {key} must contain strings")
    if values.get("schema_version") != 1:
        raise ValueError("config requires schema_version = 1")
    if values.get("min_bytes", 0) < 0:
        raise ValueError("min_bytes must be zero or greater")
    if "preset" in values and values["preset"] != "documents":
        raise ValueError("preset must be documents")
    # Validate types/schema globally, selectors after precedence for applicable actions.
    source = values.get("repo")
    if source is not None and (not source or "\0" in source or source.startswith("-")):
        raise ValueError("config repo must be a nonempty repository path or URL, not an option")
    if source is not None and (source.startswith(("/", "./", "../", "~"))
                               or ":" not in source.split("/", 1)[0]):
        values["repo"] = str((path.parent / Path(source).expanduser()).resolve())
    return values


def resolve(args):
    explicit = vars(args).copy()
    values = {}
    if not args.no_config:
        path = Path(args.config).absolute() if args.config is not None else discover(explicit.get("repo", "."))
        if path is not None and (args.config is not None or path.exists() or path.is_symlink()):
            values = read(path)
    applicable = {"json"}
    if args.command in {"analyze", "clean"}:
        applicable |= SELECTION
    elif args.command == "rebase":
        applicable |= {"repo", "branch"}
    for key in applicable:
        setattr(args, key, explicit.get(key, values.get(key, DEFAULTS[key])))
    return args
