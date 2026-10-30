# Contributing

Use Python 3.10 or newer and Git 2.36 or newer. Create a virtual environment and
install `python -m pip install -e '.[dev]'`, then run
`python -m unittest discover -s tests -v`.

Preserve the separation between snapshot, rewrite, verification and publication.
Never test destructive operations against a real remote: tests create temporary
repositories and local bare remotes. Safety changes need regression cases that
exercise Git, especially shared blob contents, branch/tag scope, tree equality,
lease failures, malformed paths and backup retention.

Keep console behavior, CLI reference, migration notes and changelog consistent.
Build both wheel and sdist and run `python -m twine check --strict dist/*` before
requesting a release. Validate installation from a wheel in a separate virtual
environment. See [releasing](docs/releasing.md) for PyPI instructions.

## Source installation

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python -m build
python -m twine check --strict dist/*
```

Tests create temporary local repositories and bare remotes; they never push to a
hosted service. The GitHub workflows test macOS/Linux and build the distribution.
Publishing is a separate, manually dispatched workflow using PyPI Trusted
Publishing; see the release guide for the required account configuration.

MIT licensed. See [LICENSE](LICENSE).

