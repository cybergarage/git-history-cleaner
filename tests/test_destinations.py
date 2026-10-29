"""Concrete destination precedence and original-source inference on disposable remotes."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import git_history_cleaner
from git_history_cleaner import core, destinations
from git_history_cleaner.cli import main
from test_workflow import Fixture


class Destinations(Fixture):
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
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def remotes(self):
        self.old_asset()
        paths = [self.root / (name + '.git') for name in ('a', 'b', 'c')]
        for path in paths:
            core.git(self.root, 'clone', '--bare', str(self.repo), str(path))
        return paths

    def clean_cli(self, *extra):
        code, out, err = self.cli('clean', '--repo', str(self.repo), '--path', 'assets', '--json', *extra)
        self.assertEqual(0, code, err)
        return json.loads(out)

    def test_original_remote_hierarchy_pushurl_and_ambiguity(self):
        a, b, c = self.remotes()
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        self.assertEqual(str(a), destinations.original(str(self.repo), 'main')['destination'])
        core.git(self.repo, 'remote', 'add', 'publish', str(b))
        self.assertIn('ambiguous', destinations.original(str(self.repo), 'main')['error'])
        core.git(self.repo, 'config', 'branch.main.remote', 'origin')
        self.assertEqual(str(a), destinations.original(str(self.repo), 'main')['destination'])
        core.git(self.repo, 'config', 'remote.pushDefault', 'publish')
        self.assertEqual(str(b), destinations.original(str(self.repo), 'main')['destination'])
        core.git(self.repo, 'config', 'branch.main.pushRemote', 'origin')
        core.git(self.repo, 'config', 'remote.origin.pushurl', '../c.git')
        self.assertEqual(str(c), destinations.original(str(self.repo), 'main')['destination'])
        core.git(self.repo, 'config', '--add', 'remote.origin.pushurl', str(b))
        self.assertIn('multiple', destinations.original(str(self.repo), 'main')['error'])
        core.git(self.repo, 'config', '--unset-all', 'remote.origin.pushurl')
        core.git(self.repo, 'config', '--add', 'remote.origin.url', str(c))
        self.assertIn('multiple', destinations.original(str(self.repo), 'main')['error'])
        core.git(self.repo, 'config', 'branch.main.pushRemote', '.')
        self.assertIn('itself', destinations.original(str(self.repo), 'main')['error'])
        core.git(self.repo, 'config', 'branch.main.pushRemote', 'missing')
        self.assertIn('missing', destinations.original(str(self.repo), 'main')['error'])

    def test_cli_over_config_over_saved_source_and_relative_config_path(self):
        a, b, c = self.remotes()
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        settings = self.root / 'settings'
        settings.mkdir()
        config = settings / 'selection.toml'
        config.write_text('schema_version = 1\nremote = "../b.git"\njson = false\n')
        with self.cwd(self.repo):
            result = self.clean_cli('--config', str(config))
            before_config = (self.repo / '.git/config').read_bytes()
            code, out, err = self.cli('push', '--remote', str(c), '--yes')
            self.assertEqual(0, code, err)
            self.assertIn('CLI --remote', err)
            self.assertIn(str(c), err)
            self.assertEqual(result['new_head'], core.text(c, 'rev-parse', 'main'))
            self.assertEqual(result['old_head'], core.text(a, 'rev-parse', 'main'))
            self.assertEqual(result['old_head'], core.text(b, 'rev-parse', 'main'))
            self.assertEqual(before_config, (self.repo / '.git/config').read_bytes())
            self.assertEqual(result['old_head'], core.text(self.repo, 'rev-parse', 'HEAD'))
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
            result = self.clean_cli('--config', str(config))
            code, out, err = self.cli('push', '--yes')
            self.assertEqual(0, code, err)
            self.assertIn('TOML remote', err)
            self.assertEqual(result['new_head'], core.text(b, 'rev-parse', 'main'))

    def test_subprocess_inferred_pushurl_then_rebase_uses_recorded_destination(self):
        a, b, _ = self.remotes()
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        core.git(self.repo, 'config', 'remote.origin.pushurl', str(b))
        original_config = (self.repo / '.git/config').read_bytes()
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(git_history_cleaner.__file__).resolve().parent.parent)
        def command(*args):
            proc = subprocess.run([sys.executable, '-m', 'git_history_cleaner', *args], cwd=self.repo,
                                  env=env, text=True, capture_output=True, timeout=30)
            self.assertEqual(0, proc.returncode, proc.stderr)
            return proc
        result = json.loads(command('clean', '--path', 'assets', '--json').stdout)
        pushed = command('push', '--yes', '--json')
        self.assertIn('original remote origin', pushed.stderr)
        self.assertEqual(str(b), json.loads(pushed.stdout)['destination'])
        self.assertEqual(result['old_head'], core.text(a, 'rev-parse', 'main'))
        self.assertEqual(result['old_head'], core.text(self.repo, 'rev-parse', 'HEAD'))
        self.assertEqual(original_config, (self.repo / '.git/config').read_bytes())
        command('rebase')  # origin fetch URL is a, but default migration must fetch b.
        self.assertEqual(result['new_head'], core.text(self.repo, 'rev-parse', 'HEAD'))
        self.assertEqual(str(a), core.text(self.repo, 'remote', 'get-url', 'origin'))
        command('cleanup', '--yes')

    def test_source_push_policy_is_frozen_and_config_remote_is_live(self):
        a, b, c = self.remotes()
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        with self.cwd(self.repo):
            result = self.clean_cli()
            core.git(self.repo, 'remote', 'set-url', 'origin', str(c))
            code, out, err = self.cli('push', '--yes')
            self.assertEqual(0, code, err)
            self.assertEqual(result['new_head'], core.text(a, 'rev-parse', 'main'))
            self.assertEqual(result['old_head'], core.text(c, 'rev-parse', 'main'))
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
            config = self.repo / '.git-history-cleaner'
            config.write_text('schema_version = 1\nremote = "../b.git"\n')
            result = self.clean_cli()
            config.write_text('schema_version = 1\nremote = "../c.git"\n')
            self.assertEqual(0, self.cli('push', '--yes')[0])
            self.assertEqual(result['new_head'], core.text(c, 'rev-parse', 'main'))
            self.assertEqual(result['old_head'], core.text(b, 'rev-parse', 'main'))

    def test_saved_config_context_outside_scope_and_removed_config_refusal(self):
        a, b, _ = self.remotes()
        config = self.root / 'explicit.toml'
        config.write_text('schema_version = 1\nremote = "b.git"\n')
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        with self.cwd(self.repo):
            result = self.clean_cli('--config', str(config))
        with self.cwd(self.root):
            config.unlink()
            code, out, err = self.cli('push', '--run', result['run'], '--yes')
            self.assertEqual(1, code)
            self.assertIn('explicit.toml', err)
            config.write_text('schema_version = 1\nremote = "b.git"\n')
            self.assertEqual(0, self.cli('push', '--run', result['run'], '--yes')[0])
            self.assertEqual(result['new_head'], core.text(b, 'rev-parse', 'main'))

    def test_no_config_and_explicit_config_override_saved_context(self):
        a, b, c = self.remotes()
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        config = self.root / 'saved.toml'
        config.write_text('schema_version = 1\nremote = "b.git"\n')
        other = self.root / 'other.toml'
        other.write_text('schema_version = 1\nremote = "c.git"\n')
        with self.cwd(self.repo):
            result = self.clean_cli('--config', str(config))
            self.assertEqual(0, self.cli('push', '--config', str(other), '--yes')[0])
            self.assertEqual(result['new_head'], core.text(c, 'rev-parse', 'main'))
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
            result = self.clean_cli('--config', str(config))
            self.assertEqual(0, self.cli('push', '--no-config', '--yes')[0])
            self.assertEqual(result['new_head'], core.text(a, 'rev-parse', 'main'))

    def test_remote_source_url_fallback_and_missing_or_ambiguous_policy_refusal(self):
        a, b, _ = self.remotes()
        with self.cwd(self.root):
            code, out, err = self.cli('clean', '--repo', a.as_uri(), '--path', 'assets', '--json')
            self.assertEqual(0, code, err)
            result = json.loads(out)
            self.assertEqual(0, self.cli('push', '--yes')[0])
            self.assertEqual(result['new_head'], core.text(a, 'rev-parse', 'main'))
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
        with self.cwd(self.repo):
            result = self.clean_cli()
            self.assertEqual(1, self.cli('push', '--yes')[0])
            self.assertEqual(0, self.cli('cleanup', '--yes')[0])
            core.git(self.repo, 'remote', 'add', 'one', str(a))
            core.git(self.repo, 'remote', 'add', 'two', str(b))
            result = self.clean_cli()
            code, out, err = self.cli('push', '--yes')
            self.assertEqual(1, code)
            self.assertIn('ambiguous', err)
            self.assertEqual(0, self.cli('push', '--remote', str(b), '--yes')[0])

    def test_self_target_and_isolated_origin_are_not_used(self):
        self.old_asset()
        with self.cwd(self.repo):
            result = self.clean_cli()
            self.assertEqual(1, self.cli('push', '--remote', str(self.repo), '--yes')[0])
            self.assertEqual(1, self.cli('push', '--remote', result['repository'], '--yes')[0])
            self.assertEqual(1, self.cli('push', '--remote', 'origin', '--yes')[0])
            self.assertEqual(1, self.cli('push', '--yes')[0])
            self.assertEqual(result['old_head'], core.text(self.repo, 'rev-parse', 'HEAD'))

    def test_invalid_flat_remote_and_empty_cli_are_not_inherited(self):
        a, b, _ = self.remotes()
        config = self.root / 'config.toml'
        with self.cwd(self.repo):
            for value in ('false', '[]', '""', '"-bad"', '"ext::sh -c unsafe"', '"unknown://host/repo"', '"file:///invalid%FF"'):
                config.write_text('schema_version = 1\nremote = ' + value + '\n')
                before = set((self.repo / '.git').iterdir())
                self.assertEqual(1, self.cli('clean', '--config', str(config), '--path', 'assets')[0])
                self.assertEqual(before, set((self.repo / '.git').iterdir()))
            config.write_text('schema_version = 1\nremote = "b.git"\njson = true\n')
            result = self.clean_cli('--config', str(config))
            self.assertEqual(1, self.cli('push', '--remote', '', '--yes')[0])
            self.assertEqual(result['old_head'], core.text(b, 'rev-parse', 'main'))
            code, out, err = self.cli('push', '--no-json', '--yes')
            self.assertEqual(0, code, err)
            self.assertTrue(out.startswith('pushed:'))

    def test_generic_push_settings_do_not_expand_refs(self):
        a, _, _ = self.remotes()
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        core.git(self.repo, 'config', 'remote.origin.mirror', 'true')
        core.git(self.repo, 'config', 'remote.origin.push', '+refs/heads/*:refs/heads/copied/*')
        with self.cwd(self.repo):
            result = self.clean_cli()
            repo = Path(result['repository'])
            core.git(repo, 'config', 'push.followTags', 'true')
            core.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                     'tag', '-a', 'do-not-publish', '-m', 'fixture')
            self.assertEqual(0, self.cli('push', '--yes')[0])
            self.assertEqual('refs/heads/main', core.text(a, 'for-each-ref', '--format=%(refname)'))

    def test_trailing_empty_repeated_git_preferences_and_urls_are_ambiguous(self):
        a, b, _ = self.remotes()
        core.git(self.repo, 'remote', 'add', 'origin', str(a))
        for key in ('branch.main.pushRemote', 'remote.pushDefault', 'branch.main.remote'):
            core.git(self.repo, 'config', '--add', key, 'origin')
            core.git(self.repo, 'config', '--add', key, '')
            self.assertIn('ambiguous', destinations.original(str(self.repo), 'main')['error'])
            core.git(self.repo, 'config', '--unset-all', key)
        core.git(self.repo, 'config', 'remote.origin.pushurl', str(b) + '\r')
        self.assertIn('error', destinations.original(str(self.repo), 'main'))
        core.git(self.repo, 'config', '--unset-all', 'remote.origin.pushurl')
        for urls in ((str(b), ''), ('', str(b))):
            for value in urls:
                core.git(self.repo, 'config', '--add', 'remote.origin.pushurl', value)
            self.assertIn('multiple', destinations.original(str(self.repo), 'main')['error'])
            core.git(self.repo, 'config', '--unset-all', 'remote.origin.pushurl')

    def test_trailing_space_in_local_pushurl_is_preserved(self):
        self.old_asset()
        plain = self.root / 'remote.git'
        spaced = self.root / 'remote.git '
        for target in (plain, spaced):
            core.git(self.root, 'clone', '--bare', str(self.repo), str(target))
        core.git(self.repo, 'remote', 'add', 'origin', str(spaced))
        with self.cwd(self.repo):
            result = self.clean_cli()
            self.assertEqual(0, self.cli('push', '--yes')[0])
            self.assertEqual(result['new_head'], core.text(spaced, 'rev-parse', 'main'))
            self.assertEqual(result['old_head'], core.text(plain, 'rev-parse', 'main'))
