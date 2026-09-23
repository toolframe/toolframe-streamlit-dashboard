# CI and package publishing

`Python CI` runs on pull requests, pushes (including tags), manual dispatches and
calls from the publishing workflow. It uses Python **3.14.7** and uv **0.12.8** on
`ubuntu-24.04` and `macos-15`. Actions are pinned to full commit IDs. Default
permissions are `contents: read`; checkout credentials are not persisted.
The reusable CI has no concurrency group that could cancel its publishing caller.

## Run the same checks locally

From this Git checkout, with uv 0.12.8 and the SDK repository available locally:

```sh
uv run --isolated --no-project --python 3.14.7 python -I scripts/validate.py
```

The default SDK location is `../toolframe-sdk`. Use `--sdk-source /path/to/toolframe-sdk`
for another checkout. Optionally pass `--output-dir /path/to/empty-directory`;
otherwise the script creates an artifact directory in the OS temporary directory
and prints its path. The output directory must be empty to prevent stale artifacts
from passing as new results. It contains `dist/`, the SDK dependency wheel,
`pytest.xml`, installed runtime dependencies and a JSON report with SHA-256 hashes.

The command creates a new source snapshot, SDK source copy, wheelhouse and two
environments. uv may reuse its upstream download cache; the package/SDK wheels
are freshly built and both installation environments start empty.
It does not use or modify a repository's `.venv`, `dist`,
`uv.lock`, or SDK working tree. The source snapshot includes this repository's
current tracked changes and non-ignored new files, so local edits can be checked
before committing. SDK source always comes from commit
`121e60eb5ba77717a382cd474c7a31d2de086d13`, regardless of its checked-out branch.

The validation sequence is:

1. Build the pinned SDK wheel and this package's sdist/wheel with
   `uv build --no-sources`. Verify that both package archives preserve `LICENSE`
   and `NOTICE` byte for byte.
2. Install the package and SDK wheels with real runtime dependencies and the
   existing `dev` dependency group into a fresh validation environment. Run
   `uv pip check`, `ruff check src tests scripts`, all existing tests with
   `pytest -q` from an empty working directory against the installed wheel, and
   Twine **7.0.0** `twine check --strict` on both distributions.
   [Twine 7](https://twine.readthedocs.io/en/stable/changelog.html#twine-7-0-0-2026-07-27)
   supports the Metadata-Version 2.5 emitted by current Hatchling.
3. Install both wheels and their runtime dependencies into a second new
   environment, without development dependencies. Run `uv pip check`, import
   the dashboard modules, SDK, Streamlit and Uvicorn, load the plugin entry point,
   and verify installed `app.py`/`chrome.css` assets from an empty working directory.
   Python isolated mode and import path checks ensure these imports come from
   the installed wheels.

The existing dashboard lifecycle test still launches fresh SDK worker subprocesses
for the first and replacement generations, checks their real Streamlit HTTP
endpoints, and disposes each process. Streamlit process singletons are not reset
or reused to avoid running that test. Dependency-graph, history and management
tests remain part of the full suite.

The management test helper permits up to 60 seconds for the initial AppTest run.
In a fresh local macOS environment, the first pandas native-module import
exceeded the original 10-second script timeout (26 passed, one timed out;
confirmed by a pytest faulthandler thread dump). Later interactions keep the
existing 10-second default. Every assertion and lifecycle worker boundary remains
in place; there are no retries, skips or mocked dependency imports.

The clean installation resolves the existing version ranges from package metadata;
it does not rewrite the development lockfile or turn local source overrides into
published requirements. `installed.txt` records the actual runtime resolution.
Temporary source/environments are removed when the command finishes; keep or
remove the printed artifact directory as needed.

## GitHub prerequisites

The default dependency repository is
`${github.repository_owner}/toolframe-sdk`. Set the repository Actions variable
`TOOLFRAME_REPOSITORY_OWNER` only if the SDK belongs to a different trusted owner.
For a fork pull request the fallback remains the base repository owner; the
workflow never derives it from the pull request's contributor. Push the SDK's
exact pinned commit to that owner before running remote CI.

The checked-in workflow assumes that the SDK can be read publicly. A default
repository `GITHUB_TOKEN` does not grant access to another private repository.
Private SDK hosting needs an explicitly configured read-only GitHub App/token
checkout arrangement, including a decision about fork PR access, before CI can
run there. No credential or owner has been invented in these files.

## Publish to TestPyPI or PyPI

`Publish Python package` is manual only. It defaults to `testpypi`; select `pypi`
explicitly for production. A push, pull request or CI run cannot upload a package.
The dispatch must target the exact `v<project.version>` tag; the current version
requires `v0.4.1`. Branch dispatches and mismatched versions fail the release gate.

Before a future upload:

1. Configure this repository's GitHub remote, push the workflows and SDK commit,
   and create/push the version tag on the intended release commit. The workflow
   must also exist on the default branch for manual dispatch to be available.
2. Create GitHub environments named **testpypi** and **pypi**. Configure appropriate
   tag restrictions and required reviewers, especially for `pypi`.
3. In TestPyPI and PyPI separately, configure a Trusted Publisher (or pending
   publisher for a new project) for `toolframe-streamlit-dashboard`: the actual
   GitHub owner, repository **toolframe-streamlit-dashboard**, workflow filename
   **publish.yml**, and the matching **testpypi** or **pypi** environment name.
   No long-lived PyPI API token is required.
4. Ensure `toolframe-sdk==0.2.0` is available on the intended consumer index before
   advertising an index-only installation. CI's SDK wheel is a validation input;
   this workflow uploads only the dashboard package.
5. Dispatch `publish.yml` at the version tag with the selected repository, for
   example `gh workflow run publish.yml --ref v0.4.1 -f repository=testpypi`.

Publishing reruns both CI matrix jobs on the dispatched commit, then downloads
the Ubuntu distribution artifact from **that same workflow run**. It never
rebuilds after validation or downloads artifacts from a separate PR run. The
upload job alone has `id-token: write` and uses the PyPA publishing action in the
selected GitHub environment. SDK wheels and verification reports are separate
artifacts and cannot enter the upload directory. Existing package versions are
not silently skipped; plan a new version/tag for subsequent releases.

See the official [uv CI guide](https://docs.astral.sh/uv/guides/integration/github/),
[GitHub runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
and [PyPI Trusted Publishing guide](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

## Validation limits

Local verification exercises the dashboard package on the local macOS architecture.
The configured Ubuntu/macOS matrix still needs an actual GitHub Actions run.
Package tests do not establish support for the full Toolframe application on
Linux, Windows or physical Intel hardware. OIDC upload, GitHub environment rules,
remote dependency checkout and browser behavior in the complete application are
not established by local package verification or actionlint. Preparing these
files does not push a commit, upload a package or execute a remote deployment.
