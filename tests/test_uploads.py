"""Publication recovery against local bare remotes; no hosted test writes."""
import json
from pathlib import Path
from unittest import mock

from git_history_cleaner import core, uploads
from test_workflow import Fixture


class Uploads(Fixture):
    def remote(self):
        bare = self.root / "remote.git"
        core.git(self.root, "clone", "--bare", str(self.repo), str(bare))
        return bare

    def test_byte_plan_splits_and_covers_final_commit(self):
        for index in range(6):
            self.write(f"asset{index}.txt", str(index) * 150000)
            self.commit(f"asset {index}")
        budget = 1400000
        plan = uploads.checkpoints(self.repo, 0, budget)
        self.assertGreater(len(plan), 1)
        self.assertTrue(all(bound <= budget for _, bound in plan))
        self.assertEqual(core.text(self.repo, "rev-parse", "HEAD"), plan[-1][0])

    def test_oversized_single_commit_rejected_before_remote_write(self):
        result = self.clean()
        bare = self.remote()
        # Make old/new different, so this exercises planning rather than the
        # already-published shortcut.
        self.old_asset()
        core.git(bare, "fetch", str(self.repo), "main:main")
        core.cleanup(result["run"], True)
        result = self.clean()
        original = core.git
        calls = []
        def tracking(repo, *args, **kwargs):
            if args[0] == "push":
                calls.append(args)
            return original(repo, *args, **kwargs)
        with mock.patch.object(core, "git", side_effect=tracking):
            with self.assertRaisesRegex(ValueError, "cannot split"):
                core.push(result["run"], str(bare), True, max_push_bytes=1024)
        self.assertEqual([], calls)
        self.assertEqual(result["old_head"], core.text(bare, "rev-parse", "main"))

    def test_resume_retains_successful_checkpoints_and_skips_them(self):
        self.old_asset()
        result = self.clean()
        bare = self.remote()
        original = core.git
        successful = []
        def fail_second(repo, *args, **kwargs):
            if args[0] == "push" and ":refs/heads/git-history-cleaner-" in args[-1]:
                if successful:
                    raise RuntimeError("simulated HTTP 500")
                output = original(repo, *args, **kwargs)
                successful.append(args[-1])
                return output
            return original(repo, *args, **kwargs)
        with mock.patch.object(core, "git", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                core.push(result["run"], str(bare), True, chunk_size=1)
        manifest = json.loads((Path(result["run"]) / "run.json").read_text())
        self.assertEqual("push-failed", manifest["state"])
        self.assertTrue(manifest["temporary_refs"])
        def resume(repo, *args, **kwargs):
            if args[0] == "push":
                self.assertNotIn(args[-1], successful)
            return original(repo, *args, **kwargs)
        with mock.patch.object(core, "git", side_effect=resume):
            answer = core.push(result["run"], str(bare), True, chunk_size=1)
        self.assertEqual([], answer["temporary_refs_remaining"])
        self.assertEqual(result["new_head"], core.text(bare, "rev-parse", "main"))

    def test_lost_success_response_is_reconciled_and_repeat_does_not_push(self):
        self.old_asset()
        result = self.clean()
        bare = self.remote()
        original = core.git
        def lost_response(repo, *args, **kwargs):
            output = original(repo, *args, **kwargs)
            if args[0] == "push" and args[-1].endswith(":refs/heads/main"):
                raise RuntimeError("HTTP 500 after update")
            return output
        with mock.patch.object(core, "git", side_effect=lost_response):
            self.assertTrue(core.push(result["run"], str(bare), True)["pushed"])
        def no_push(repo, *args, **kwargs):
            self.assertNotEqual("push", args[0])
            return original(repo, *args, **kwargs)
        with mock.patch.object(core, "git", side_effect=no_push):
            self.assertTrue(core.push(result["run"], str(bare), True)["pushed"])
