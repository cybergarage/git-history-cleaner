"""Concrete push destinations captured from original sources, never isolated origins."""
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import core


def local_path(value):
    if value.startswith('file://'):
        parsed = urlsplit(value)
        if parsed.netloc not in ('', 'localhost') or not parsed.path.startswith('/'):
            raise ValueError('file destination must name an absolute local path')
        return Path(unquote(parsed.path, errors='strict')).resolve()
    if value.startswith(('/', './', '../', '~')) or ':' not in value.split('/', 1)[0]:
        return Path(value).expanduser().resolve()
    return None


def normalize(value, base=None):
    if type(value) is not str or not value or value.isspace() or any(c in value for c in ('\0', '\n', '\r')) or value.startswith('-'):
        raise ValueError('remote must be a nonempty destination URL/path, not an option')
    if '://' in value and urlsplit(value).scheme not in {'http', 'https', 'ssh', 'git', 'file', 'git+ssh', 'ssh+git'}:
        raise ValueError('unsupported destination URL protocol')
    if '::' in value and '://' not in value:
        raise ValueError('remote helper command destinations are unsupported; use a standard Git URL/path')
    # URL/scp forms remain URLs; ordinary strings are filesystem paths, never remote nicknames.
    if value.startswith('file://'):
        return str(local_path(value))
    if value.startswith(('/', './', '../', '~')) or ':' not in value.split('/', 1)[0]:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path(base or Path.cwd()) / path
        return str(path.resolve())
    return value


def values(repo, key):
    try:
        raw = core.git(repo, 'config', '--null', '--get-all', key)
    except RuntimeError as exc:
        if not str(exc):  # git config exits 1 with empty stderr for a missing key.
            return []
        raise
    return raw.decode('utf-8', 'surrogateescape').split('\0')[:-1]


def original(source, branch):
    """Snapshot the original push policy at clean time; errors need explicit override later."""
    try:
        if not Path(source).exists():
            return {'destination': normalize(source), 'origin': 'saved source URL'}
        remote = None
        for key in (f'branch.{branch}.pushRemote', 'remote.pushDefault', f'branch.{branch}.remote'):
            found = values(source, key)
            if found:
                if len(found) != 1 or not found[0]:
                    raise ValueError(f'ambiguous or empty original {key}; supply remote explicitly')
                remote = found[0]
                break
        names = core.git(source, 'remote').decode('utf-8', 'surrogateescape').splitlines()
        if remote is None:
            if len(names) != 1:
                raise ValueError('original source has missing or ambiguous push remotes; supply remote explicitly')
            remote = names[0]
        if remote == '.':
            raise ValueError('original push policy targets the source itself; supply a different remote destination')
        if remote not in names or remote.startswith('-'):
            raise ValueError('original push remote is missing or invalid; supply remote explicitly')
        configured = values(source, f'remote.{remote}.pushurl') or values(source, f'remote.{remote}.url')
        if len(configured) != 1 or not configured[0]:
            raise ValueError('original push remote has multiple or missing URLs; supply one destination explicitly')
        urls = core.git(source, 'remote', 'get-url', '--push', '--all', '--', remote).decode('utf-8', 'surrogateescape').split('\n')[:-1]
        if len(urls) != 1 or not urls[0]:
            raise ValueError('original push remote has multiple or missing URLs; supply one destination explicitly')
        return {'destination': normalize(urls[0], source), 'origin': f'original remote {remote}'}
    except (ValueError, RuntimeError, OSError) as exc:
        return {'error': str(exc)}


def resolve(audit, root, supplied=None, origin=None):
    if supplied is not None:
        destination = normalize(supplied)
        selected_by = origin or 'explicit destination'
    else:
        saved = audit.get('source_push')
        if not saved or saved.get('error'):
            raise ValueError((saved or {}).get('error', 'this result has no saved source push destination')
                             + '; use --remote URL/path or flat TOML remote')
        destination, selected_by = saved['destination'], saved['origin']
    path = local_path(destination)
    if path is not None:
        if path.is_relative_to(root):
            raise ValueError('refusing to push into this operation result')
        source = Path(audit['source'])
        if source.exists():
            source_git = core.text(source, 'rev-parse', '--absolute-git-dir')
            destination_git = core.text(path, 'rev-parse', '--absolute-git-dir')
            if Path(source_git).resolve() == Path(destination_git).resolve():
                raise ValueError('refusing to push into the original local source')
        if core.text(path, 'rev-parse', '--is-bare-repository') != 'true':
            raise ValueError('local push destination must be a bare repository; refusing a working tree')
    return destination, selected_by
