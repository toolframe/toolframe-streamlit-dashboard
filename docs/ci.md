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
`ef91b609137a5fe7bae8e0c893e74b096ff06ffe`, regardless of its checked-out branch.

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

## Publication

See [releasing](releasing.md) for dependency order, private repository access,
Trusted Publisher bindings, version tags and consumer installation checks.

## Validation limits

Local verification exercises the dashboard package on the local macOS architecture.
The configured Ubuntu/macOS matrix still needs an actual GitHub Actions run.
Package tests do not establish support for the full Toolframe application on
Linux, Windows or physical Intel hardware. OIDC upload, GitHub environment rules,
remote dependency checkout and browser behavior in the complete application are
not established by local package verification or actionlint. Preparing these
files does not push a commit, upload a package or execute a remote deployment.
