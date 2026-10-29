"""Issue #1: stdout, strict configuration, and plan-free isolated cleaning."""
import contextlib
import io
import json
import os
from pathlib import Path
from unittest import mock

from test_workflow import Fixture
from git_history_cleaner import core
from git_history_cleaner.cli import main


class ConfigClean(Fixture):
    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    @contextlib.contextmanager
    def cwd(self, path):
        previous = Path.cwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(previous)

    def config(self, body, root=None):
        path = (root or self.repo) / '.git-history-cleaner'
        path.write_text('schema_version = 1\n' + body)
        return path

    def test_stdout_without_artifacts_and_redirection(self):
        self.old_asset()
        with self.cwd(self.root):
            before = set(self.root.iterdir())
            code, out, err = self.invoke('analyze', '--repo', str(self.repo), '--path', 'assets')
            self.assertEqual((0, ''), (code, err))
            self.assertIn('strip_blobs:', out)
            code, out, err = self.invoke('analyze', '--repo', str(self.repo), '--ext', 'pdf', '--json')
            self.assertEqual(0, code, err)
            self.assertTrue(json.loads(out)['strip_blobs'])
            self.assertEqual(before, set(self.root.iterdir()))
            with (self.root / 'report.json').open('w') as stream, contextlib.redirect_stdout(stream):
                self.assertEqual(0, main(['analyze', '--repo', str(self.repo), '--ext', 'pdf', '--json']))
            self.assertIn('rules', json.loads((self.root / 'report.json').read_text()))

    def test_clean_and_push_with_no_plan_io(self):
        self.old_asset()
        self.config('repo = "."\npath = ["assets"]\next = ["pdf"]\njson = true\n')
        old = core.text(self.repo, 'rev-parse', 'HEAD')
        original_save = core.save
        def no_plan_save(path, value):
            self.assertNotEqual('plan.json', path.name)
            original_save(path, value)
        with self.cwd(self.repo), mock.patch.object(core, 'save', side_effect=no_plan_save):
            code, out, err = self.invoke('clean')
        self.assertEqual(0, code, err)
        result = json.loads(out)
        self.assertTrue(result['verified'])
        self.assertEqual(old, core.text(self.repo, 'rev-parse', 'HEAD'))
        self.assertFalse(list(Path(result['run']).rglob('plan.json')))
        self.assertFalse((Path(result['run']) / 'backup.git').exists())
        bare = self.root / 'destination.git'
        core.git(self.root, 'clone', '--bare', str(self.repo), str(bare))
        self.assertTrue(core.push(result['run'], str(bare), True)['pushed'])
        self.assertEqual(result['new_head'], core.text(bare, 'rev-parse', 'main'))
        core.cleanup(result['run'], True)

    def test_override_zero_false_lists_preset_and_all_shared_keys(self):
        self.old_asset()
        conf = self.config('repo = "."\nbranch = "main"\npath = ["wrong"]\nexclude = ["assets"]\n'
                           'ext = ["zip"]\npreset = "documents"\nmin_bytes = 999999\njson = true\n')
        code, out, err = self.invoke('analyze', '--config', str(conf), '--path', 'assets', '--exclude', 'other',
                                     '--ext', 'txt', '--ext', 'pdf', '--min-bytes', '0', '--no-json')
        self.assertEqual(0, code, err)
        self.assertIn('strip_blobs:', out)
        self.assertIn('"paths": ["assets"]', out)
        self.assertIn('"min_bytes": 0', out)
        self.assertIn('".docx"', out)
        code, out, err = self.invoke('analyze', '--no-config', '--repo', str(self.repo))
        self.assertEqual(1, code)
        self.assertIn('specify --path', err)

    def test_discovery_nested_worktree_explicit_repo_and_single_pass(self):
        self.config('repo = "."\npath = ["assets"]\njson = true\n')
        nested = self.repo / 'nested'
        nested.mkdir()
        with self.cwd(nested):
            self.assertEqual(0, self.invoke('analyze')[0])
        with self.cwd(self.root):
            self.assertEqual(0, self.invoke('analyze', '--repo', str(self.repo))[0])
        worktree = self.root / 'linked'
        core.git(self.repo, 'worktree', 'add', '-b', 'linked', str(worktree))
        self.config('path = ["assets"]\n', worktree)
        with self.cwd(worktree):
            self.assertEqual(0, self.invoke('analyze')[0])
        second = self.root / 'second'
        core.git(self.root, 'clone', str(self.repo), str(second))
        self.config('yes = true\n', second)
        self.config('repo = "../second"\npath = ["assets"]\n')
        with self.cwd(self.repo):
            self.assertEqual(0, self.invoke('analyze')[0])

    def test_invalid_configuration_before_side_effects(self):
        bad = ['yes = true', '[clean]\npath = ["assets"]', 'action = "clean"', 'schema_version = 2',
               'min_bytes = -1', 'json = 0', 'ext = "pdf"', 'path = [1]', 'preset = "other"',
               'path = ["../bad"]', 'exclude = ["assets"]', 'path = ["assets"']
        with self.cwd(self.root), mock.patch.object(core, 'clean', side_effect=AssertionError('must not clean')):
            # Schema validation happens in CLI; resolved selection validation happens in core.
            for body in bad[:9]:
                conf = self.root / 'config'
                conf.write_text(('' if body.startswith('schema_version') else 'schema_version = 1\n') + body)
                code, out, err = self.invoke('clean', '--config', str(conf))
                self.assertEqual(1, code, body)
                self.assertTrue(err)
        for body in bad[9:]:
            conf = self.config(body)
            with self.cwd(self.root):
                before = set(self.root.iterdir())
                self.assertEqual(1, self.invoke('clean', '--config', str(conf))[0])
                self.assertEqual(before, set(self.root.iterdir()))
        missing = self.root / 'missing'
        self.assertEqual(1, self.invoke('analyze', '--config', str(missing))[0])
        link = self.root / 'link.toml'
        link.symlink_to(conf)
        self.assertEqual(1, self.invoke('analyze', '--config', str(link))[0])

    def test_bare_and_remote_never_load_downloaded_config(self):
        self.config('yes = true\n')
        self.commit('invalid configuration in source')
        bare = self.root / 'bare.git'
        core.git(self.root, 'clone', '--bare', str(self.repo), str(bare))
        (bare / '.git-history-cleaner').write_text('invalid')
        for source in (str(bare), self.repo.as_uri()):
            with self.cwd(self.root):
                code, out, err = self.invoke('analyze', '--repo', source, '--path', 'assets')
                self.assertEqual(0, code, err)

    def test_independent_clean_uses_current_source_and_config(self):
        self.old_asset()
        self.config('path = ["missing"]\njson = true\n')
        with self.cwd(self.repo):
            self.assertFalse(json.loads(self.invoke('analyze')[1])['strip_blobs'])
            self.config('path = ["assets"]\njson = true\n')
            self.write('assets/new.pdf', 'old extra')
            self.commit('extra')
            self.write('assets/new.pdf', 'current extra')
            self.commit('extra current')
            expected = core.text(self.repo, 'rev-parse', 'HEAD')
            result = json.loads(self.invoke('clean')[1])
            self.assertEqual(expected, result['old_head'])
            self.assertNotEqual(result['old_head'], result['new_head'])

    def test_source_change_during_clean_rejected(self):
        self.old_asset()
        original_git = core.git
        def changed(repo, *args, **kwargs):
            if args[0] == 'clone' and str(args[-1]).endswith('/rewritten'):
                self.write('changed', 'concurrent')
                self.commit('concurrent')
            return original_git(repo, *args, **kwargs)
        with self.cwd(self.root), mock.patch.object(core, 'git', side_effect=changed):
            code, out, err = self.invoke('clean', '--no-config', '--repo', str(self.repo), '--path', 'assets')
        self.assertEqual(1, code)
        self.assertIn('changed during clean', err)

    def test_remote_clean_and_policy_independent_of_later_config(self):
        self.old_asset()
        with self.cwd(self.root):
            code, out, err = self.invoke('clean', '--repo', self.repo.as_uri(), '--branch', 'main',
                                         '--ext', 'pdf', '--json')
            self.assertEqual(0, code, err)
            result = json.loads(out)
            self.config('path = ["README"]\n', self.root)
            self.assertTrue(core.verify(result['run'])['verified'])
            # An exported report can never become the source of a later clean.
            self.assertFalse((Path(result['run']) / 'plan.json').exists())
            audit_path = Path(result['run']) / 'audit.json'
            audit = json.loads(audit_path.read_text())
            audit['selection']['strip_blobs'] = []
            audit_path.write_text(json.dumps(audit))
            with self.assertRaisesRegex(ValueError, 'audit changed'):
                core.verify(result['run'])

    def test_config_cannot_bypass_push_or_cleanup_confirmation(self):
        self.old_asset()
        with self.cwd(self.root):
            result = json.loads(self.invoke('clean', '--repo', str(self.repo), '--ext', 'pdf', '--json')[1])
            self.config('json = true\n', self.root)
            bare = self.root / 'remote.git'
            core.git(self.root, 'clone', '--bare', str(self.repo), str(bare))
            with mock.patch('sys.stdin.isatty', return_value=False):
                self.assertEqual(1, self.invoke('push', '--run', result['run'], '--remote', str(bare))[0])
                self.assertEqual(1, self.invoke('cleanup', '--run', result['run'])[0])
            self.assertTrue(Path(result['run']).exists())
            self.assertEqual(result['old_head'], core.text(bare, 'rev-parse', 'main'))

    def test_empty_lists_and_completed_policy_unchanged_by_configuration(self):
        self.old_asset()
        conf = self.config('path = []\nexclude = []\next = []\njson = false\n')
        code, out, err = self.invoke('analyze', '--config', str(conf))
        self.assertEqual(1, code)
        self.assertIn('specify --path', err)
        result = self.clean()
        self.config('path = ["README"]\n')
        code, out, err = self.invoke('verify', '--config', str(conf), '--run', result['run'])
        self.assertEqual(0, code, err)
        self.assertIn('verified: true', out)

    def test_raw_git_publish_example_from_correct_result(self):
        self.old_asset()
        with self.cwd(self.root):
            result = json.loads(self.invoke('clean', '--repo', str(self.repo), '--ext', 'pdf', '--json')[1])
        bare = self.root / 'remote.git'
        core.git(self.root, 'clone', '--bare', str(self.repo), str(bare))
        core.git(result['repository'], 'push', '--force-with-lease=refs/heads/main:' + result['old_head'],
                 str(bare), result['new_head'] + ':refs/heads/main')
        self.assertEqual(result['new_head'], core.text(bare, 'rev-parse', 'main'))
        self.assertEqual('verified', core.load_run(result['run'])[1]['state'])

    def test_clean_rebase_and_cleanup(self):
        self.old_asset()
        bare = self.root / 'remote.git'
        core.git(self.root, 'clone', '--bare', str(self.repo), str(bare))
        clone = self.root / 'existing'
        core.git(self.root, 'clone', str(bare), str(clone))
        with self.cwd(self.root):
            result = json.loads(self.invoke('clean', '--repo', str(self.repo), '--ext', 'pdf', '--json')[1])
            core.push(result['run'], str(bare), True)
            code, out, err = self.invoke('rebase', '--no-config', '--repo', str(clone), '--run', result['run'])
            self.assertEqual(0, code, err)
            self.assertEqual(result['new_head'], core.text(clone, 'rev-parse', 'HEAD'))
            self.assertEqual(0, self.invoke('cleanup', '--no-config', '--run', result['run'], '--yes')[0])

    def test_config_cli_branch_and_repo_overrides(self):
        self.old_asset()
        conf = self.config('repo = "missing"\nbranch = "missing"\next = ["pdf"]\n')
        code, out, err = self.invoke('analyze', '--config', str(conf), '--repo', str(self.repo), '--branch', 'main')
        self.assertEqual(0, code, err)
        self.assertIn('strip_blobs:', out)
        # Invalid remote selection must fail before even a temporary inspection clone.
        with mock.patch.object(core, 'clone_inspection', side_effect=AssertionError('must not clone')):
            for extra in (['--branch', 'bad..name'], ['--path', '../bad']):
                self.assertEqual(1, self.invoke('clean', '--no-config', '--repo', 'https://example.invalid/repo',
                                                '--ext', 'pdf', *extra)[0])

    def test_relative_config_paths_and_colon_named_local_repository(self):
        self.old_asset()
        named = self.root / 'source:archive'
        core.git(self.root, 'clone', str(self.repo), str(named))
        settings = self.root / 'settings'
        settings.mkdir()
        conf = settings / 'selection.toml'
        conf.write_text('schema_version = 1\nrepo = "../source:archive"\npath = ["assets"]\njson = true\n')
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        with self.cwd(elsewhere):
            code, out, err = self.invoke('analyze', '--config', '../settings/selection.toml')
            self.assertEqual(0, code, err)
            result = json.loads(out)
            self.assertEqual(str(named), result['source'])
            self.assertTrue(result['strip_blobs'])
            # The CLI repository path is relative to invocation, not the config file.
            code, out, err = self.invoke('analyze', '--config', '../settings/selection.toml', '--repo', '../source')
            self.assertEqual(0, code, err)
            self.assertEqual(str(self.repo), json.loads(out)['source'])

    def test_explicit_empty_values_do_not_fall_back(self):
        from git_history_cleaner import config
        from git_history_cleaner.cli import parser
        self.config('repo = "."\npath = ["assets"]\nexclude = ["keep"]\next = ["pdf"]\njson = true\n')
        with self.cwd(self.repo):
            # Empty CLI strings are invalid values, never a request to inherit config.
            for option in ('--config', '--repo', '--branch', '--path', '--exclude', '--ext'):
                code, out, err = self.invoke('clean', option, '')
                self.assertEqual(1, code, (option, out, err))
                self.assertTrue(err)
            # Resolution also preserves explicit empty list values if supplied by a caller.
            args = parser().parse_args(['analyze', '--no-json', '--min-bytes', '0'])
            args.path, args.ext, args.exclude = [], [], []
            resolved = config.resolve(args)
            self.assertEqual(([], [], [], 0, False),
                             (resolved.path, resolved.ext, resolved.exclude, resolved.min_bytes, resolved.json))
            code, out, err = self.invoke('analyze', '--no-json')
            self.assertEqual(0, code, err)
            self.assertTrue(out.startswith('source:'))
            self.assertFalse(list(self.repo.glob('.git-history-cleaner-*')))

    def test_nested_clean_with_implicit_repository(self):
        self.old_asset()
        self.config('path = ["assets"]\njson = true\n')
        nested = self.repo / 'nested'
        nested.mkdir()
        original = core.text(self.repo, 'rev-parse', 'HEAD')
        with self.cwd(nested):
            code, out, err = self.invoke('clean')
        self.assertEqual(0, code, err)
        self.assertTrue(json.loads(out)['verified'])
        self.assertEqual(original, core.text(self.repo, 'rev-parse', 'HEAD'))

    def test_default_head_switch_or_detach_during_clean_rejected(self):
        self.old_asset()
        core.git(self.repo, 'branch', 'other')
        original = core.text(self.repo, 'rev-parse', 'HEAD')
        real_git = core.git
        for checkout in (('checkout', 'other'), ('checkout', '--detach')):
            real_git(self.repo, 'checkout', 'main')
            def switching(repo, *args, **kwargs):
                result = real_git(repo, *args, **kwargs)
                if args[0] == 'clone' and str(args[-1]).endswith('/rewritten'):
                    real_git(self.repo, *checkout)
                return result
            with self.cwd(self.root), mock.patch.object(core, 'git', side_effect=switching):
                code, out, err = self.invoke('clean', '--no-config', '--repo', str(self.repo), '--ext', 'pdf')
            self.assertEqual(1, code, err)
            self.assertIn('source HEAD changed', err)
            self.assertEqual(original, core.text(self.repo, 'rev-parse', 'HEAD'))
            self.assertEqual(original, core.text(self.repo, 'rev-parse', 'main'))
            with self.cwd(self.root):
                self.assertEqual(0, self.invoke('cleanup', '--no-config', '--yes')[0])

    def test_clean_zero_targets_and_filter_failure_preserve_original(self):
        self.old_asset()
        original = core.text(self.repo, 'rev-parse', 'HEAD')
        with self.cwd(self.root):
            code, out, err = self.invoke('clean', '--no-config', '--repo', str(self.repo), '--path', 'missing', '--json')
            self.assertEqual(0, code, err)
            result = json.loads(out)
            self.assertTrue(result['verified'])
            self.assertEqual(original, result['new_head'])
            self.assertEqual('main', result['branch'])
            self.assertEqual(original, core.text(self.repo, 'rev-parse', 'HEAD'))
            self.assertEqual(0, self.invoke('cleanup', '--no-config', '--yes')[0])
            real_git = core.git
            def failing(repo, *args, **kwargs):
                if args[0] == 'filter-repo':
                    raise RuntimeError('synthetic filtering failure')
                return real_git(repo, *args, **kwargs)
            before = set(self.root.glob('.git-history-cleaner-result-*'))
            with mock.patch.object(core, 'git', side_effect=failing):
                code, out, err = self.invoke('clean', '--no-config', '--repo', str(self.repo), '--ext', 'pdf')
            self.assertEqual(1, code)
            self.assertIn('synthetic filtering failure', err)
            failed = (set(self.root.glob('.git-history-cleaner-result-*')) - before).pop()
            self.assertEqual('failed', json.loads((failed / 'run.json').read_text())['state'])
            self.assertFalse((failed / 'audit.json').exists())
            self.assertFalse((failed / 'plan.json').exists())
            self.assertFalse((failed / 'strip-blobs.txt').exists())
            self.assertEqual(original, core.text(self.repo, 'rev-parse', 'HEAD'))

    def test_all_command_sections_refused_before_artifacts(self):
        with self.cwd(self.root):
            for command in ('analyze', 'clean', 'rewrite', 'verify', 'push', 'rebase', 'cleanup'):
                path = self.config(f'[{command}]\njson = true\n')
                before = set(self.root.iterdir())
                code, out, err = self.invoke('clean', '--config', str(path))
                self.assertEqual(1, code)
                self.assertIn('unsupported config key/section', err)
                self.assertEqual(before, set(self.root.iterdir()))

    def test_readme_commands_through_subprocess_cli(self):
        import subprocess
        import sys
        import git_history_cleaner
        self.old_asset()
        core.git(self.repo, 'branch', 'other')
        core.git(self.repo, 'tag', 'release')
        original = core.text(self.repo, 'rev-parse', 'HEAD')
        remote = self.root / 'remote.git'
        core.git(self.root, 'clone', '--bare', str(self.repo), str(remote))
        existing = self.root / 'existing'
        core.git(self.root, 'clone', str(remote), str(existing))
        core.git(existing, 'config', 'user.name', 'Fixture')
        core.git(existing, 'config', 'user.email', 'fixture@example.invalid')
        (existing / 'local.txt').write_text('unpublished work')
        core.git(existing, 'add', 'local.txt')
        core.git(existing, 'commit', '-qm', 'local work')
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(git_history_cleaner.__file__).resolve().parent.parent)
        def cli(*args, stdout=subprocess.PIPE):
            result = subprocess.run([sys.executable, '-m', 'git_history_cleaner', *args],
                                    cwd=self.repo, env=env, text=True, stdout=stdout, stderr=subprocess.PIPE)
            self.assertEqual(0, result.returncode, result.stderr)
            return result.stdout
        before = set(self.repo.iterdir())
        self.assertIn('strip_blobs:', cli('analyze', '--no-config', '--repo', '.', '--path', 'assets', '--ext', 'pdf,png,jpg'))
        self.assertEqual(before, set(self.repo.iterdir()))
        with (self.root / 'analysis.json').open('w') as redirected:
            cli('analyze', '--no-config', '--repo', '.', '--ext', 'pdf', '--json', stdout=redirected)
        self.assertTrue(json.loads((self.root / 'analysis.json').read_text())['strip_blobs'])
        output = cli('clean', '--no-config', '--repo', '.', '--path', 'assets', '--ext', 'pdf,png,jpg')
        result = {key: json.loads(value) for key, value in (line.split(': ', 1) for line in output.splitlines())}
        self.assertTrue(result['verified'])
        self.assertEqual('main', result['branch'])
        self.assertEqual(original, core.text(self.repo, 'rev-parse', 'HEAD'))
        self.assertIn('verified: true', cli('verify', '--no-config'))
        # The shortest documented publication command discovers the unique result.
        self.assertIn('pushed: true', cli('push', '--no-config', '--remote', str(remote), '--yes'))
        self.assertEqual(result['new_head'], core.text(remote, 'rev-parse', 'main'))
        self.assertEqual(original, core.text(remote, 'rev-parse', 'other'))
        self.assertEqual(original, core.text(remote, 'rev-parse', 'release'))
        self.assertIn('rebased:', cli('rebase', '--no-config', '--repo', str(existing), '--remote', 'origin'))
        self.assertEqual('unpublished work', (existing / 'local.txt').read_text())
        self.assertEqual(result['new_head'], core.text(existing, 'rev-parse', 'HEAD~1'))
        fresh = self.root / 'project-fresh'
        core.git(self.root, 'clone', str(remote), str(fresh))
        self.assertEqual(result['new_head'], core.text(fresh, 'rev-parse', 'HEAD'))
        self.assertIn('deleted:', cli('cleanup', '--no-config', '--yes'))

    def test_remote_default_head_switch_is_refused(self):
        self.old_asset()
        core.git(self.repo, 'branch', 'other')
        original = core.text(self.repo, 'rev-parse', 'HEAD')
        real_git = core.git
        def switching(repo, *args, **kwargs):
            result = real_git(repo, *args, **kwargs)
            if args[0] == 'clone' and str(args[-1]).endswith('/rewritten'):
                real_git(self.repo, 'checkout', 'other')
            return result
        with self.cwd(self.root), mock.patch.object(core, 'git', side_effect=switching):
            code, out, err = self.invoke('clean', '--no-config', '--repo', self.repo.as_uri(), '--ext', 'pdf')
        self.assertEqual(1, code, err)
        self.assertIn('source HEAD changed', err)
        self.assertEqual(original, core.text(self.repo, 'rev-parse', 'HEAD'))

    def test_new_commands_never_read_or_write_a_plan(self):
        self.old_asset()
        real_open = Path.open
        def guarded_open(path, *args, **kwargs):
            self.assertNotIn('plan', path.name)
            return real_open(path, *args, **kwargs)
        with self.cwd(self.root), mock.patch.object(Path, 'open', autospec=True, side_effect=guarded_open):
            self.assertEqual(0, self.invoke('analyze', '--repo', str(self.repo), '--ext', 'pdf')[0])
            code, out, err = self.invoke('clean', '--repo', str(self.repo), '--ext', 'pdf', '--json')
            self.assertEqual(0, code, err)
            self.assertTrue(json.loads(out)['verified'])

    def test_only_current_commands_and_options_are_accepted(self):
        import argparse
        from git_history_cleaner.cli import parser
        command_parser = parser()
        commands = next(action for action in command_parser._actions
                        if isinstance(action, argparse._SubParsersAction)).choices
        self.assertEqual({'analyze', 'clean', 'verify', 'push', 'rebase', 'cleanup'}, set(commands))
        for args in (['analyze-legacy'], ['rewrite', '--plan', 'old/plan.json'],
                     ['analyze', '--work-dir', 'old'], ['clean', '--plan', 'old/plan.json'],
                     ['cleanup', '--run', 'old', '--include-backup']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                main(args)
            self.assertEqual(2, failure.exception.code)
        self.assertFalse(hasattr(core, 'legacy_analyze'))
        self.assertFalse(hasattr(core, 'rewrite'))
        self.assertFalse(hasattr(core, 'load_plan'))

    def test_saved_plan_runs_are_rejected_without_modification(self):
        import uuid
        old = self.root / 'old-run'
        old.mkdir()
        marker = old / 'run.json'
        marker.write_text(json.dumps({'format': core.FORMAT, 'root': str(old),
                                     'run_id': str(uuid.uuid4()), 'state': 'verified',
                                     'plan_digest': 'old-plan-digest'}))
        plan = old / 'plan.json'
        plan.write_text('{"old": "execution plan"}')
        before = {p.name: p.read_bytes() for p in old.iterdir()}
        for command in (['verify'], ['push', '--remote', str(self.root / 'remote.git'), '--yes'],
                        ['rebase', '--repo', str(self.repo)], ['cleanup', '--yes']):
            with mock.patch.object(core, 'git', side_effect=AssertionError('must not touch a repository')):
                code, out, err = self.invoke(*command, '--no-config', '--run', str(old))
            self.assertEqual(1, code)
            self.assertIn('unsupported saved-plan run', err)
            self.assertEqual(before, {p.name: p.read_bytes() for p in old.iterdir()})
