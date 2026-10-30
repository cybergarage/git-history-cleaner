"""Command-line interface. Remote writes are always explicit."""
import argparse
import json
from pathlib import Path
import sys

from . import __version__, core, config, operations, uploads


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def parser():
    result = argparse.ArgumentParser(description="Clean obsolete Git history while preserving the current tree.")
    result.add_argument("--version", action="version", version=__version__)
    sub = result.add_subparsers(dest="command", required=True)
    for name, help_text in (("analyze", "inspect selection to stdout without saving a plan"),
                            ("clean", "rewrite and verify an isolated clone without a plan")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--repo", default=argparse.SUPPRESS, help="local repository or clone URL (default: .)")
        command.add_argument("--branch", default=argparse.SUPPRESS, help="branch (default: source HEAD branch)")
        for option in ("path", "exclude", "ext"):
            command.add_argument("--" + option, action="append", default=argparse.SUPPRESS,
                                 help="repeatable literal selector; extensions also accept comma-separated values")
        command.add_argument("--preset", choices=["documents"], default=argparse.SUPPRESS)
        command.add_argument("--min-bytes", type=nonnegative, default=argparse.SUPPRESS)
    verify = sub.add_parser("verify", help="verify tree preservation, removals and Git integrity")
    verify.add_argument("--run", help="optional expert scope anchor; never bypasses ambiguity")
    push = sub.add_parser("push", help="explicitly publish a verified rewrite using a lease")
    push.add_argument("--run", help="optional expert scope anchor; never bypasses ambiguity")
    push.add_argument("--remote", default=argparse.SUPPRESS, help="destination URL/bare path; default TOML remote, then saved original source")
    push.add_argument("--yes", action="store_true")
    push.add_argument("--push-chunk-size", type=nonnegative, default=0)
    push.add_argument("--max-push-bytes", type=nonnegative, default=uploads.DEFAULT_MAX_BYTES,
                      help="conservative bytes per upload (default: 1.5 GiB; must be positive)")
    cleanup = sub.add_parser("cleanup", help="confirm cleanup of all proven operation artifacts in this scope")
    cleanup.add_argument("--run", help="optional expert scope anchor; never bypasses ambiguity")
    cleanup.add_argument("--yes", action="store_true")
    rebase = sub.add_parser("rebase", help="replay local commits onto a rewritten branch; preserve a backup")
    rebase.add_argument("--run", help="optional expert scope anchor; never bypasses ambiguity")
    rebase.add_argument("--repo", default=argparse.SUPPRESS)
    rebase.add_argument("--remote", help="optional fetch remote name/URL; default recorded successful push destination")
    rebase.add_argument("--branch", default=argparse.SUPPRESS, help="local branch (default: branch recorded in audit)")
    for command in sub.choices.values():
        formatting = command.add_mutually_exclusive_group()
        formatting.add_argument("--json", dest="json", action="store_true", default=argparse.SUPPRESS,
                                help="emit machine-readable results")
        formatting.add_argument("--no-json", dest="json", action="store_false", default=argparse.SUPPRESS)
        configuration = command.add_mutually_exclusive_group()
        configuration.add_argument("--config", help="explicit local TOML file")
        configuration.add_argument("--no-config", action="store_true", help="disable repository configuration")
    return result


def rebase_run(args):
    root, manifest = core.load_run(args.run)
    if manifest["state"] != "pushed":
        raise ValueError("rebase requires a successfully pushed run")
    audit = core.load_audit(root, manifest)
    repo = Path(args.repo).resolve()
    branch = args.branch or audit["branch"]
    core.git(repo, "check-ref-format", "refs/heads/" + branch)
    remote = args.remote if args.remote is not None else manifest.get("destination")
    if not remote or remote.startswith("-"):
        raise ValueError("remote must not start with '-'")
    if core.text(repo, "status", "--porcelain"):
        raise ValueError("local working tree must be clean")
    # Fetch into FETCH_HEAD: do not depend on tracking configuration.
    core.git(repo, "fetch", "--no-tags", "--recurse-submodules=no", remote, "refs/heads/" + audit["branch"])
    onto = core.text(repo, "rev-parse", "FETCH_HEAD")
    if onto != manifest["new_head"]:
        raise ValueError("remote tip does not match this run; inspect subsequent commits manually")
    core.git(repo, "merge-base", "--is-ancestor", audit["old_head"], "refs/heads/" + branch)
    backup = "backup-before-history-cleaner-" + manifest["run_id"]
    core.git(repo, "branch", backup, "refs/heads/" + branch)
    try:
        # Also handles zero local commits, moving the branch to the new base.
        core.git(repo, "rebase", "--rebase-merges", "--onto", onto, audit["old_head"], branch)
    except RuntimeError as exc:
        raise RuntimeError(f"{exc}\nBackup retained: {backup}. Resolve and rebase --continue, or rebase --abort.") from exc
    return {"rebased": branch, "backup_branch": backup}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command != "push":
            args = config.resolve(args)
        if args.command == "clean":
            result = core.clean(args)
        elif args.command == "analyze":
            result = core.analyze(args)
        elif args.command == "cleanup":
            result = core.cleanup(args.run, args.yes)
        else:
            with operations.operation(args.run) as root:
                if args.command == "verify":
                    result = core.verify(root)
                elif args.command == "push":
                    _, manifest = core.load_run(root)
                    args = config.resolve(args, context=manifest.get("configuration"))
                    result = core.push(root, args.remote, args.yes, args.push_chunk_size, args._destination_origin, args.max_push_bytes)
                else:
                    args.run = str(root)
                    result = rebase_run(args)
        if args.json:
            print(json.dumps(result, ensure_ascii=True))
        else:
            for key, value in result.items():
                print(f"{key}: {json.dumps(value, ensure_ascii=True)}")
        return 0
    except (RuntimeError, ValueError, OSError, KeyError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
