# Prepare and publish 1.0.0

The distribution name is `git-history-cleaner`, the import name is
`git_history_cleaner`, and the executable is `git-history-cleaner`.
The license is MIT. Package metadata and `__version__` must agree on `1.0.0`.
The GitHub repository is `cybergarage/git-history-cleaner`.
Publisher settings must use this repository name.

A PyPI account alone does not configure uploads. Use Trusted Publishing to avoid
storing a long-lived PyPI token in GitHub. The workflow does not publish on push,
tag creation, or GitHub Release creation; publication requires manual dispatch.

## 1. Validate locally

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python -m build
python -m twine check --strict dist/*
```

Build in a clean checkout or empty `dist` directory so only the intended version
is present. Install the resulting wheel in another environment:

```sh
python3 -m venv /tmp/history-cleaner-release-check
/tmp/history-cleaner-release-check/bin/python -m pip install dist/git_history_cleaner-1.0.0-py3-none-any.whl
/tmp/history-cleaner-release-check/bin/git-history-cleaner --version
/tmp/history-cleaner-release-check/bin/python -m unittest discover -s tests -v
```

Inspect sdist contents (source, documentation, tests and license), confirm CI on
macOS/Linux and Python 3.10/3.14, and review the compatibility and safety notes.
Local validation is not evidence that GitHub CI or a hosted remote push succeeded.

## 2. Configure the publisher

In PyPI's account publishing settings, add a pending publisher for a new project:

| Field | Value |
| --- | --- |
| PyPI project name | `git-history-cleaner` |
| GitHub owner | `cybergarage` |
| GitHub repository | `git-history-cleaner` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

Create the `pypi` environment in that GitHub repository. Configure a required
reviewer where your GitHub plan supports it. Repeat on TestPyPI with a separate
TestPyPI account/publisher and the environment name `testpypi`. TestPyPI and PyPI
accounts/configuration are independent.

If the package name has become unavailable, stop and choose a new name rather
than uploading under an unrelated project. A 404 from the project JSON API is an
availability indication, not a reservation or proof that registration will be
accepted. Do not paste account tokens into issue bodies, commits, or chat.

References: [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
and [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

## 3. Tag and test the distribution

After review, mark the changelog release date, commit the release, and create and
push the `v1.0.0` tag. These are release operations, not performed by the build.
Run **Publish distribution** manually on tag `v1.0.0`, destination `testpypi`.
The workflow requires the tag to match the package version and runs tests and
wheel validation before upload.

Download only this package from TestPyPI, then install its dependencies from PyPI:

```sh
python -m pip download --no-deps --index-url https://test.pypi.org/simple/ \
  --dest /tmp/history-cleaner-testpypi git-history-cleaner==1.0.0
python -m pip install /tmp/history-cleaner-testpypi/git_history_cleaner-1.0.0-py3-none-any.whl
```

Use a fresh environment to test the downloaded release. Avoid assuming all
runtime dependencies are present on TestPyPI. If published files need changes,
use a new version; package index files cannot simply be overwritten.

## 4. Publish

After TestPyPI verification, manually run the workflow on the same reviewed tag
with destination `pypi`. It builds and uploads wheel and sdist using OIDC. Do not
advance or replace the tag between TestPyPI verification and PyPI publication.
Then verify an installation from PyPI in a clean environment:

```sh
pipx install git-history-cleaner==1.0.0
git-history-cleaner --version
git-history-cleaner --help
```

Publish GitHub release notes from the changelog and record the actual PyPI URL.
A local wheel, a tag, or a completed build is not evidence of successful upload.
