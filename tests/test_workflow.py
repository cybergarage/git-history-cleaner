"""Real temporary repositories; never use a user's remote for integration tests."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from git_history_cleaner import core
from git_history_cleaner.cli import main


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="history-cleaner-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "source"
        self.repo.mkdir()
        core.git(self.repo, "init", "-b", "main")
        core.git(self.repo, "config", "user.name", "Fixture")
        core.git(self.repo, "config", "user.email", "fixture@example.invalid")
        self.write("README", "baseline")
        self.commit("initial")

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(self, message):
        core.git(self.repo, "add", "-A")
        core.git(self.repo, "commit", "-qm", message)

    def analyze(self, **kwargs):
        options = dict(repo=str(self.repo), branch=None, path=["assets"], exclude=[],
                       ext=["pdf"], preset=None, min_bytes=0)
        options.update(kwargs)
        return core.analyze(argparse.Namespace(**options))

    def old_asset(self):
        self.write("assets/document.pdf", "obsolete")
        self.commit("old")
        self.write("assets/document.pdf", "current")
        self.commit("new")

    def clean(self, **kwargs):
        options = dict(repo=str(self.repo), branch=None, path=["assets"], exclude=[],
                       ext=["pdf"], preset=None, min_bytes=0)
        options.update(kwargs)
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            return core.clean(argparse.Namespace(**options))
        finally:
            os.chdir(previous)


class Workflow(Fixture):
    def test_full_workflow_and_short_preload(self):
        self.old_asset()
        before = core.text(self.repo, "rev-parse", "HEAD")
        result = self.clean()
        self.assertTrue(result["head_tree_preserved"])
        self.assertNotEqual(before, result["new_head"])
        self.assertEqual(before, core.text(self.repo, "rev-parse", "HEAD"))
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        pushed = core.push(result["run"], str(bare), yes=True, chunk_size=100)
        self.assertEqual([], pushed["temporary_refs_remaining"])
        self.assertEqual(result["new_head"], core.text(bare, "rev-parse", "refs/heads/main"))
        self.assertEqual("refs/heads/main", core.text(bare, "for-each-ref", "--format=%(refname)"))

    def test_protect_head_across_extensions_and_deleted_shared_path(self):
        self.write("assets/old.pdf", "shared")
        self.commit("old")
        (self.repo / "assets/old.pdf").unlink()
        self.write("current.txt", "shared")
        self.commit("reuse with another extension")
        result = self.analyze()
        self.assertEqual([], result["strip_blobs"])
        self.assertEqual(["assets/old.pdf"], result["deleted_paths"])
        cleaned = self.clean()
        self.assertEqual("shared", core.text(cleaned["repository"], "show", "HEAD:current.txt"))

    def test_outside_historical_content_is_protected(self):
        self.write("assets/file.pdf", "shared")
        self.write("outside.txt", "shared")
        self.commit("shared")
        self.write("assets/file.pdf", "new")
        self.write("outside.txt", "updated")
        self.commit("new")
        result = self.analyze()
        self.assertEqual([], result["strip_blobs"])
        self.assertGreater(result["protected_outside_blobs"], 0)
        self.clean()

    def test_special_filenames(self):
        names = ["assets/日本語.pdf", "assets/white space.pdf", "assets/tab\tname.pdf", "assets/new\nline.pdf",
                 "assets/#hash.pdf", "assets/glob:*.pdf", "assets/quote'\".pdf"]
        for name in names:
            self.write(name, name)
        self.commit("names")
        for name in names:
            (self.repo / name).unlink()
        self.commit("remove names")
        result = self.analyze()
        self.assertEqual(set(names), set(result["deleted_paths"]))
        self.clean()

    def test_excluded_paths_and_size(self):
        self.write("assets/small.pdf", "a")
        self.write("assets/keep/big.pdf", "b" * 100)
        self.write("assets/large.pdf", "c" * 100)
        self.commit("old")
        for path in ("assets/small.pdf", "assets/keep/big.pdf", "assets/large.pdf"):
            (self.repo / path).unlink()
        self.commit("delete")
        result = self.analyze(exclude=["assets/keep"], min_bytes=20)
        self.assertEqual(["assets/large.pdf"], result["deleted_paths"])
        self.clean(exclude=["assets/keep"], min_bytes=20)

    def test_source_branch_default_not_main(self):
        core.git(self.repo, "branch", "-m", "trunk")
        self.old_asset()
        result = self.analyze()
        self.assertEqual("trunk", result["branch"])
        self.clean()

    def test_other_branches_and_tags_unchanged(self):
        self.old_asset()
        core.git(self.repo, "tag", "release")
        core.git(self.repo, "branch", "other")
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        original = core.text(bare, "rev-parse", "release")
        result = self.clean()
        core.push(result["run"], str(bare), True)
        self.assertEqual(original, core.text(bare, "rev-parse", "release"))
        self.assertEqual(original, core.text(bare, "rev-parse", "other"))

    def test_merge_history(self):
        self.old_asset()
        core.git(self.repo, "checkout", "-qb", "side")
        self.write("side.txt", "side")
        self.commit("side")
        core.git(self.repo, "checkout", "main")
        self.write("main.txt", "main")
        self.commit("main")
        core.git(self.repo, "merge", "--no-ff", "side", "-m", "merge")
        self.assertTrue(self.clean()["verified"])

    def test_changed_audit_refused(self):
        self.old_asset()
        result = self.clean()
        path = Path(result["run"]) / "audit.json"
        audit = json.loads(path.read_text())
        audit["selection"]["deleted_paths"].append("README")
        path.write_text(json.dumps(audit))
        with self.assertRaisesRegex(ValueError, "audit changed"):
            core.verify(result["run"])

    def test_changed_destination_refused(self):
        self.old_asset()
        result = self.clean()
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        core.git(bare, "update-ref", "refs/heads/main", core.text(self.repo, "rev-parse", "HEAD~1"))
        with self.assertRaisesRegex(ValueError, "differs"):
            core.push(result["run"], str(bare), True)

    def test_verify_rejects_changed_head(self):
        self.old_asset()
        result = self.clean()
        repo = Path(result["repository"])
        core.git(repo, "reset", "--hard", "HEAD~1")
        with self.assertRaisesRegex(ValueError, "HEAD changed"):
            core.verify(result["run"])

    def test_cleanup_requires_recognized_clean_run(self):
        self.old_asset()
        result = self.clean()
        unrelated = self.root / "git-compress-unrelated"
        unrelated.mkdir()
        with self.assertRaises(OSError):
            core.cleanup(unrelated, True)
        self.assertTrue(unrelated.exists())
        core.cleanup(result["run"], True)
        self.assertFalse(Path(result["run"]).exists())

    def test_cleanup_rejects_symlink_and_unexpected_content(self):
        result = self.clean()
        link = self.root / "link"
        link.symlink_to(result["run"])
        with self.assertRaisesRegex(ValueError, "symlink"):
            core.cleanup(link, True)
        (Path(result["run"]) / "personal.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            core.cleanup(result["run"], True)

    def test_zero_changes_and_single_commit(self):
        result = self.clean()
        self.assertEqual(result["old_head"], result["new_head"])
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        core.push(result["run"], str(bare), True, 100)

    def test_rebase_zero_and_local_commits(self):
        self.old_asset()
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        clones = []
        for index in range(2):
            clone = self.root / f"clone{index}"
            core.git(self.root, "clone", str(bare), str(clone))
            core.git(clone, "config", "user.name", "Fixture")
            core.git(clone, "config", "user.email", "fixture@example.invalid")
            clones.append(clone)
        (clones[1] / "local.txt").write_text("local")
        core.git(clones[1], "add", ".")
        core.git(clones[1], "commit", "-qm", "local")
        result = self.clean()
        core.push(result["run"], str(bare), True)
        for clone in clones:
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["rebase", "--run", result["run"], "--repo", str(clone)])
            self.assertEqual(0, code)
            self.assertIn("backup-before-history-cleaner-", core.text(clone, "branch", "--list"))
        self.assertEqual("local", (clones[1] / "local.txt").read_text())

    def test_remote_advance_during_push_is_rejected_by_lease(self):
        self.old_asset()
        result = self.clean()
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        self.write("new.txt", "concurrent")
        self.commit("concurrent")
        concurrent = core.text(self.repo, "rev-parse", "HEAD")
        original_git = core.git
        def advancing_git(repo, *args, **kwargs):
            if args[0] == "push" and any("--force-with-lease=refs/heads/main:" in a for a in args):
                original_git(self.repo, "push", str(bare), "HEAD:refs/heads/main")
            return original_git(repo, *args, **kwargs)
        with mock.patch.object(core, "git", side_effect=advancing_git):
            with self.assertRaises(RuntimeError):
                core.push(result["run"], str(bare), True)
        self.assertEqual(concurrent, core.text(bare, "rev-parse", "main"))
        manifest = json.loads((Path(result["run"]) / "run.json").read_text())
        self.assertEqual("push-failed", manifest["state"])

    def test_failed_preload_cleanup_retains_record(self):
        self.old_asset()
        result = self.clean()
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        original_git = core.git
        def failing_git(repo, *args, **kwargs):
            if args[0] == "push" and args[-1].startswith(":refs/heads/git-history-cleaner-"):
                raise RuntimeError("simulated cleanup rejection")
            return original_git(repo, *args, **kwargs)
        with mock.patch.object(core, "git", side_effect=failing_git):
            pushed = core.push(result["run"], str(bare), True, 100)
        self.assertTrue(pushed["temporary_refs_remaining"])
        with self.assertRaisesRegex(ValueError, "temporary"):
            core.cleanup(result["run"], True)

    def test_preload_cleanup_does_not_delete_concurrent_change(self):
        self.old_asset()
        result = self.clean()
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        old = core.text(self.repo, "rev-parse", "HEAD")
        original_git = core.git
        def changing_git(repo, *args, **kwargs):
            if args[0] == "push" and args[-1].startswith(":refs/heads/git-history-cleaner-"):
                original_git(bare, "update-ref", args[-1][1:], old)
            return original_git(repo, *args, **kwargs)
        with mock.patch.object(core, "git", side_effect=changing_git):
            pushed = core.push(result["run"], str(bare), True, 100)
        remaining = pushed["temporary_refs_remaining"]
        self.assertTrue(remaining)
        self.assertEqual(old, core.text(bare, "rev-parse", remaining[0]))

    def test_noninteractive_push_does_not_write(self):
        self.old_asset()
        result = self.clean()
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        with mock.patch("sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "not confirmed"):
                core.push(result["run"], str(bare))
        self.assertEqual(result["old_head"], core.text(bare, "rev-parse", "main"))

    def test_shallow_history_rejected(self):
        self.old_asset()
        shallow = self.root / "shallow"
        core.git(self.root, "clone", "--depth=1", self.repo.as_uri(), str(shallow))
        with self.assertRaisesRegex(ValueError, "shallow"):
            self.analyze(repo=str(shallow))

    def test_file_modes_symlink_and_renames(self):
        self.write("assets/before.pdf", "old")
        self.commit("old name")
        core.git(self.repo, "mv", "assets/before.pdf", "assets/after.pdf")
        self.write("assets/after.pdf", "new")
        self.write("script", "#!/bin/sh\n")
        (self.repo / "script").chmod(0o755)
        (self.repo / "link").symlink_to("assets/after.pdf")
        self.commit("rename and modes")
        self.assertTrue(self.clean()["head_tree_preserved"])

    def test_json_failure(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            code = main(["verify", "--run", str(self.root / "missing"), "--json"])
        self.assertEqual(1, code)
        self.assertIn("error", json.loads(output.getvalue()))

    def test_empty_head_retains_commit_history(self):
        self.old_asset()
        (self.repo / "README").unlink()
        (self.repo / "assets/document.pdf").unlink()
        self.commit("empty current tree")
        count = core.text(self.repo, "rev-list", "--count", "HEAD")
        result = self.clean(path=["."], ext=[])
        self.assertTrue(result["verified"])
        self.assertEqual(count, core.text(result["repository"], "rev-list", "--count", "HEAD"))

    def test_invalid_paths(self):
        for path in ("../outside", "/absolute", ".git/config", "a/../b"):
            with self.assertRaises(ValueError):
                core.literal_path(path)


if __name__ == "__main__":
    unittest.main()
