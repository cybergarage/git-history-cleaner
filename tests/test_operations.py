"""Run-free discovery, process exclusion and conservative artifact cleanup."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from unittest import mock

import git_history_cleaner
from git_history_cleaner import core, operations
from git_history_cleaner.cli import main
from test_workflow import Fixture


class Operations(Fixture):
    @contextlib.contextmanager
    def cwd(self, path):
        previous = Path.cwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(previous)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*args, '--no-config'])
        return code, out.getvalue(), err.getvalue()

    def options(self, **values):
        defaults = dict(repo=str(self.repo), branch=None, path=['assets'], exclude=[], ext=['pdf'],
                        preset=None, min_bytes=0)
        defaults.update(values)
        return argparse.Namespace(**defaults)

    def env(self):
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(git_history_cleaner.__file__).resolve().parent.parent)
        return env

    def test_local_run_free_workflow_including_default_rebase(self):
        self.old_asset()
        old = core.text(self.repo, 'rev-parse', 'HEAD')
        remote = self.root / 'remote.git'
        core.git(self.root, 'clone', '--bare', str(self.repo), str(remote))
        core.git(self.repo, 'remote', 'add', 'origin', str(remote))
        nested = self.repo / 'nested'
        nested.mkdir()
        with self.cwd(nested):
            code, out, err = self.cli('clean', '--path', 'assets', '--ext', 'pdf', '--json')
            self.assertEqual(0, code, err)
            result = json.loads(out)
            marker = Path(result['marker'])
            self.assertEqual(self.repo / '.git', marker.parent)
            self.assertEqual('', core.text(self.repo, 'status', '--porcelain'))
            self.assertEqual(old, core.text(self.repo, 'rev-parse', 'HEAD'))
            self.assertEqual(0, self.cli('verify')[0])
            self.assertEqual(0, self.cli('push', '--remote', str(remote), '--yes')[0])
            self.assertEqual(0, self.cli('rebase')[0])
            self.assertEqual(result['new_head'], core.text(self.repo, 'rev-parse', 'HEAD'))
            self.assertIn('backup-before-history-cleaner-', core.text(self.repo, 'branch', '--list'))
            code, out, err = self.cli('cleanup', '--yes', '--json')
            self.assertEqual(0, code, err)
            self.assertEqual([result['run']], json.loads(out)['deleted'])
            self.assertIn('Cleanup 1 operation', err)
            self.assertFalse(marker.exists())
            self.assertFalse(Path(result['run']).exists())
            self.assertTrue((self.repo / '.git').is_dir())
            self.assertIn('backup-before-history-cleaner-', core.text(self.repo, 'branch', '--list'))

    def test_remote_source_and_other_clone_migration_without_run(self):
        self.old_asset()
        remote = self.root / 'remote.git'
        core.git(self.root, 'clone', '--bare', str(self.repo), str(remote))
        existing = self.root / 'existing'
        core.git(self.root, 'clone', str(remote), str(existing))
        with self.cwd(self.root):
            code, out, err = self.cli('clean', '--repo', self.repo.as_uri(), '--path', 'assets', '--json')
            self.assertEqual(0, code, err)
            result = json.loads(out)
            self.assertEqual(self.root, Path(result['marker']).parent)
            self.assertEqual(0, self.cli('push', '--remote', str(remote), '--yes')[0])
            self.assertEqual(0, self.cli('rebase', '--repo', str(existing))[0])
            self.assertEqual(result['new_head'], core.text(existing, 'rev-parse', 'HEAD'))
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])

    def test_no_result_multiple_results_and_expert_selector_rules(self):
        self.old_asset()
        with self.cwd(self.root):
            for command in (['verify'], ['push', '--remote', 'unused'], ['rebase'], ['cleanup', '--yes']):
                code, out, err = self.cli(*command)
                self.assertEqual(1, code)
                self.assertIn('no operation', err)
            first = core.clean(self.options())
            self.assertEqual(0, self.cli('verify', '--run', first['run'])[0])
            self.assertEqual(1, self.cli('clean', '--repo', str(self.repo), '--path', 'assets')[0])
            with mock.patch.object(operations, 'assert_empty'):
                second = core.clean(self.options())
            for command in (['verify'], ['push', '--remote', 'unused'], ['rebase'],
                            ['verify', '--run', first['run']]):
                code, out, err = self.cli(*command)
                self.assertEqual(1, code)
                self.assertIn('multiple operations', err)
            self.assertEqual(0, self.cli('analyze', '--repo', str(self.repo), '--path', 'assets')[0])
            unrelated = self.root / '.git-history-cleaner-unrelated.txt'
            unrelated.write_text('preserve')
            code, out, err = self.cli('cleanup', '--yes', '--json')
            self.assertEqual(0, code, err)
            self.assertEqual({first['run'], second['run']}, set(json.loads(out)['deleted']))
            self.assertTrue(unrelated.exists())
            self.assertFalse(operations.entries(self.root))
            self.assertFalse(operations.result_entries(self.root))

    def test_concurrent_clean_only_one_process_can_start(self):
        self.old_asset()
        command = [sys.executable, '-m', 'git_history_cleaner', 'clean', '--no-config', '--path', 'assets', '--json']
        processes = [subprocess.Popen(command, cwd=self.repo, env=self.env(), text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        results = [(process, process.communicate(timeout=30)) for process in processes]
        self.assertEqual([0, 1], sorted(process.returncode for process, _ in results))
        failure = next(output[1] for process, output in results if process.returncode)
        self.assertTrue('active' in failure or 'already exists' in failure, failure)
        with self.cwd(self.repo):
            directory = operations.scope()
            self.assertEqual(1, len(operations.entries(directory)))
            self.assertEqual(1, len(operations.result_entries(directory)))
            with operations.locked(directory):
                blocked = subprocess.run([sys.executable, '-m', 'git_history_cleaner', 'cleanup', '--no-config', '--yes'],
                                         cwd=self.repo, env=self.env(), text=True, capture_output=True, timeout=10)
            self.assertEqual(1, blocked.returncode)
            self.assertIn('another operation is active', blocked.stderr)
            self.assertEqual(1, len(operations.entries(directory)))

    def test_validation_and_analyze_never_create_operation_artifacts(self):
        self.old_asset()
        with self.cwd(self.root):
            before = set(self.root.iterdir())
            self.assertEqual(0, self.cli('analyze', '--repo', str(self.repo), '--path', 'assets')[0])
            for values in (['--path', '../bad'], ['--ext', ''], ['--branch', 'missing']):
                self.assertEqual(1, self.cli('clean', '--repo', str(self.repo), *values)[0])
                self.assertEqual(before, set(self.root.iterdir()))

    def test_corrupt_foreign_and_traversing_markers_never_authorize_cleanup(self):
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            good = Path(result['marker'])
            original = good.read_text()
            original_head = core.text(self.repo, 'rev-parse', 'HEAD')
            cases = ['not JSON', json.dumps({'format': 'foreign'}), json.dumps({**json.loads(original), 'result': '../source'}),
                     json.dumps({**json.loads(original), 'owner_uid': os.getuid() + 1}),
                     json.dumps({**json.loads(original), 'scope': str(self.repo)})]
            for content in cases:
                good.write_text(content)
                for command in (['verify'], ['cleanup', '--yes'], ['clean', '--repo', str(self.repo), '--path', 'assets']):
                    self.assertEqual(1, self.cli(*command)[0])
                self.assertTrue(Path(result['run']).exists())
                self.assertEqual(original_head, core.text(self.repo, 'rev-parse', 'HEAD'))
            good.write_text(original)
            foreign = self.root / (operations.PREFIX + 'foreign.json')
            foreign.write_text('unrelated document')
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertTrue(good.exists())
            self.assertTrue(foreign.exists())
            self.assertTrue(Path(result['run']).exists())

    def test_symlink_hardlink_and_nonregular_markers_are_refused(self):
        with self.cwd(self.root):
            path = self.root / (operations.PREFIX + str(uuid.uuid4()) + '.json')
            unrelated = self.root / 'unrelated'
            unrelated.write_text('preserve')
            path.symlink_to(unrelated)
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            path.unlink()
            os.link(unrelated, path)
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            path.unlink()
            os.mkfifo(path)
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertEqual('preserve', unrelated.read_text())

    def test_interrupted_reserved_and_orphan_operations(self):
        self.old_asset()
        with self.cwd(self.root):
            identifier = str(uuid.uuid4())
            marker = operations.create(self.root, {'run_id': identifier})
            self.assertEqual(1, self.cli('verify')[0])
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
            self.assertFalse(marker.exists())
            result = core.clean(self.options())
            Path(result['marker']).unlink()  # Complete owned result, interrupted marker publication.
            self.assertEqual(1, self.cli('verify')[0])
            self.assertEqual(1, self.cli('clean', '--repo', str(self.repo), '--path', 'assets')[0])
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
            result = core.clean(self.options())
            root = Path(result['run'])
            manifest = json.loads((root / 'run.json').read_text())
            manifest['state'] = 'rewriting'
            core.save(root / 'run.json', manifest)
            self.assertEqual(1, self.cli('verify')[0])
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])

    def test_cleanup_cancellation_and_changes_during_confirmation(self):
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            with mock.patch('sys.stdin.isatty', return_value=True), mock.patch('builtins.input', return_value='n'):
                code, out, err = self.cli('cleanup')
            self.assertEqual(1, code)
            self.assertIn('Cleanup 1 operation', err)
            self.assertTrue(Path(result['marker']).exists())
            self.assertTrue(Path(result['run']).exists())
            def modify(*args):
                (Path(result['run']) / 'personal.txt').write_text('keep')
            with mock.patch.object(core, 'confirm', side_effect=modify):
                self.assertEqual(1, self.cli('cleanup')[0])
            self.assertEqual('keep', (Path(result['run']) / 'personal.txt').read_text())

    def test_cleanup_preserves_backup_refs_ignored_work_and_git_metadata(self):
        self.write('.gitignore', '*.secret\n')
        self.commit('ignore fixture')
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            repo = Path(result['repository'])
            core.git(repo, 'branch', 'my-backup')
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            core.git(repo, 'branch', '-D', 'my-backup')
            (repo / 'work.secret').write_text('private')
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            (repo / 'work.secret').unlink()
            (repo / '.git/hooks/my-backup').write_text('private backup')
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertTrue((repo / '.git/hooks/my-backup').exists())

    def test_result_symlink_and_corrupted_ownership_are_refused(self):
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            root = Path(result['run'])
            marker = root / 'run.json'
            manifest = json.loads(marker.read_text())
            core.save(marker, {**manifest, 'root': str(self.repo)})
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            core.save(marker, manifest)
            root.rename(self.root / 'kept-fixture')
            root.symlink_to(self.repo)
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertTrue((self.repo / '.git').exists())

    def test_worktree_discovery_is_private_and_nested_invocation_is_stable(self):
        self.old_asset()
        linked = self.root / 'linked'
        core.git(self.repo, 'worktree', 'add', '-b', 'linked', str(linked))
        with self.cwd(self.repo):
            first = core.clean(self.options())
            first_scope = operations.scope()
        with self.cwd(linked):
            second_scope = operations.scope()
            self.assertNotEqual(first_scope, second_scope)
            second = core.clean(self.options(repo=str(linked)))
            self.assertEqual(0, self.cli('verify')[0])
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
            self.assertFalse(Path(second['marker']).exists())
        with self.cwd(self.repo):
            self.assertTrue(Path(first['marker']).exists())
            self.assertEqual(0, self.cli('verify')[0])

    def test_cleanup_never_deletes_added_object_store_backup_or_transient_named_directory(self):
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            root = Path(result['run'])
            backup = Path(result['repository']) / '.git/objects/my-backup.txt'
            backup.write_text('preserve recovery data')
            self.cli('verify')  # Verification must never refresh/bless this addition.
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertTrue(backup.exists())
            backup.unlink()
            # Removing that addition restores inventory; a foreign root directory still blocks deletion.
            foreign = root / 'strip-blobs.txt'
            foreign.mkdir()
            (foreign / 'personal.txt').write_text('preserve')
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertTrue((foreign / 'personal.txt').exists())

    def test_cleanup_preserves_commit_then_reset_recovery_history(self):
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            repo = Path(result['repository'])
            (repo / 'private.txt').write_text('unpublished work')
            core.git(repo, 'add', 'private.txt')
            core.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'local work')
            local = core.text(repo, 'rev-parse', 'HEAD')
            core.git(repo, 'reset', '--hard', result['new_head'])
            self.assertEqual('', core.text(repo, 'status', '--porcelain'))
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertIn(local, (repo / '.git/logs/HEAD').read_text())
            self.assertTrue(repo.exists())

    def test_cleanup_rejects_all_changed_report_fields(self):
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            path = Path(result['run']) / 'verification.json'
            report = json.loads(path.read_text())
            for field, value in [('branch', 'other'), ('marker', '/foreign'), ('repository', '/foreign'),
                                 ('scope', 'all branches'), ('verified', False), ('head_tree_preserved', 1)]:
                core.save(path, {**report, field: value})
                self.assertEqual(1, self.cli('cleanup', '--yes')[0])
                self.assertTrue(Path(result['marker']).exists())
            core.save(path, report)
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])

    def test_incomplete_initialization_with_unproven_directory_requires_manual_inspection(self):
        with self.cwd(self.root):
            identifier = str(uuid.uuid4())
            marker = operations.create(self.root, {'run_id': identifier})
            result = self.root / (operations.RESULT_PREFIX + identifier)
            result.mkdir()
            (result / 'personal.txt').write_text('unknown provenance')
            self.assertEqual(1, self.cli('cleanup', '--yes')[0])
            self.assertTrue(marker.exists())
            self.assertTrue((result / 'personal.txt').exists())

    def test_corrupted_explicit_scope_and_manifest_types_fail_without_traceback(self):
        self.old_asset()
        with self.cwd(self.root):
            result = core.clean(self.options())
            path = Path(result['run']) / 'run.json'
            manifest = json.loads(path.read_text())
            for field, value in [('operation_scope', []), ('state', []), ('source', None), ('run_id', 123)]:
                core.save(path, {**manifest, field: value})
                code, out, err = self.cli('verify', '--run', result['run'])
                self.assertEqual(1, code)
                self.assertNotIn('Traceback', err)
            core.save(path, manifest)
