"""Run CI against fresh source copies, environments, and distribution artifacts."""

import argparse
import hashlib
import io
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

SDK_REVISION = "539ced4dbdf9e303ec0f0205a35d65287a480b2a"
ROOT = Path(__file__).resolve().parents[1]


def run(*command, cwd, env, capture=False):
    args = [str(arg) for arg in command]
    print(f"+ {shlex.join(args)}", flush=True)
    result = subprocess.run(
        args, cwd=cwd, env=env, check=False, text=True, capture_output=capture
    )
    if result.returncode and capture:
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", file=sys.stderr, flush=True)
    result.check_returncode()
    return result.stdout.strip() if capture else None


def copy_working_tree(destination):
    # Include current edits/new files, but never ignored environments/build output.
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    for name in set(tracked.decode().split("\0")) - {""}:
        source = ROOT / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def check_licenses(source, wheel, sdist):
    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    package = project["name"].replace("-", "_")
    prefix = f"{package}-{project['version']}"
    with zipfile.ZipFile(wheel) as archive:
        for name in project["license-files"]:
            member = f"{prefix}.dist-info/licenses/{name}"
            if archive.read(member) != (source / name).read_bytes():
                raise RuntimeError(f"Wheel changed {name}")
    with tarfile.open(sdist) as archive:
        for name in project["license-files"]:
            member = f"{prefix}/{name}"
            if archive.extractfile(member).read() != (source / name).read_bytes():
                raise RuntimeError(f"sdist changed {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-source", type=Path, default=ROOT.parent / "toolframe-sdk"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="An empty directory for verified artifacts/reports",
    )
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 14):
        parser.error("Run with Python 3.14 (CI uses 3.14.7)")
    sdk_source = args.sdk_source.resolve()
    output = (
        args.output_dir.resolve()
        if args.output_dir
        else Path(tempfile.mkdtemp(prefix="dashboard-ci-artifacts-"))
    )
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(f"Output directory must be empty: {output}")

    with tempfile.TemporaryDirectory(prefix="dashboard-ci-") as temporary:
        work = Path(temporary)
        project = work / "dashboard"
        sdk = work / "sdk"
        wheelhouse = work / "wheelhouse"
        dist = work / "dist"
        empty_cwd = work / "run-cwd"
        for directory in (project, sdk, wheelhouse, dist, empty_cwd):
            directory.mkdir()
        env = os.environ.copy()
        for key in (
            "VIRTUAL_ENV",
            "CONDA_PREFIX",
            "PYTHONPATH",
            "PYTHONHOME",
            "PYTEST_ADDOPTS",
            "UV_PROJECT_ENVIRONMENT",
            "UV_PROJECT",
            "UV_WORKING_DIR",
            "UV_PYTHON",
        ):
            env.pop(key, None)
        env.update(
            UV_NO_CONFIG="true",
            PYTHONNOUSERSITE="1",
            STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",
        )
        copy_working_tree(project)
        # Read exactly the pinned commit, even if a sibling checkout is dirty/newer.
        archive = subprocess.check_output(
            ["git", "archive", "--format=tar", SDK_REVISION], cwd=sdk_source
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as source_archive:
            source_archive.extractall(sdk, filter="data")

        def execute(*command, cwd=work, capture=False):
            return run(*command, cwd=cwd, env=env, capture=capture)

        uv_version = execute("uv", "--version", capture=True)
        print(
            f"Workspace: {work}\nArtifacts: {output}\nPython: {sys.version}\n{uv_version}",
            flush=True,
        )
        execute(
            "uv",
            "build",
            "--no-sources",
            "--wheel",
            "--python",
            sys.executable,
            "--out-dir",
            wheelhouse,
            sdk,
        )
        execute(
            "uv",
            "build",
            "--no-sources",
            "--python",
            sys.executable,
            "--out-dir",
            dist,
            project,
        )
        (sdk_wheel,) = wheelhouse.glob("*.whl")
        (wheel,) = dist.glob("*.whl")
        (sdist,) = dist.glob("*.tar.gz")
        check_licenses(project, wheel, sdist)

        checks = work / "checks-env"
        execute("uv", "venv", "--python", sys.executable, checks)
        checks_python = checks / "bin" / "python"
        execute(
            "uv",
            "pip",
            "install",
            "--python",
            checks_python,
            "--no-sources",
            "--group",
            f"{project / 'pyproject.toml'}:dev",
            "twine==7.0.0",
            sdk_wheel,
            wheel,
        )
        execute("uv", "pip", "check", "--python", checks_python)
        execute(
            checks_python,
            "-I",
            "-m",
            "ruff",
            "check",
            "src",
            "tests",
            "scripts",
            cwd=project,
        )
        execute(
            checks_python,
            "-I",
            "-m",
            "pytest",
            "-q",
            "-c",
            project / "pyproject.toml",
            project / "tests",
            f"--junitxml={output / 'pytest.xml'}",
            cwd=empty_cwd,
        )
        execute(checks_python, "-I", "-m", "twine", "check", "--strict", wheel, sdist)

        # This second environment has no pytest, dev group or editable installs.
        smoke = work / "wheel-env"
        execute("uv", "venv", "--python", sys.executable, smoke)
        smoke_python = smoke / "bin" / "python"
        execute("uv", "pip", "install", "--python", smoke_python, sdk_wheel, wheel)
        execute("uv", "pip", "check", "--python", smoke_python)
        version = tomllib.loads((project / "pyproject.toml").read_text())["project"][
            "version"
        ]
        smoke_result = execute(
            smoke_python,
            "-I",
            project / "scripts" / "smoke_wheel.py",
            version,
            cwd=empty_cwd,
            capture=True,
        )
        print(smoke_result, flush=True)
        installed = execute(
            "uv", "pip", "freeze", "--python", smoke_python, capture=True
        )
        (output / "installed.txt").write_text(installed + "\n")
        report = {
            "source_revision": execute(
                "git", "rev-parse", "HEAD", cwd=ROOT, capture=True
            ),
            "working_tree": execute("git", "status", "--short", cwd=ROOT, capture=True),
            "sdk_revision": SDK_REVISION,
            "python": sys.version,
            "platform": platform.platform(),
            "uv": uv_version,
            "version": version,
            "wheel_smoke": json.loads(smoke_result),
            "sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (wheel, sdist, sdk_wheel)
            },
        }
        (output / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
        (output / "dist").mkdir()
        for path in (wheel, sdist):
            shutil.copy2(path, output / "dist" / path.name)
        (output / "dependency-wheels").mkdir()
        shutil.copy2(sdk_wheel, output / "dependency-wheels" / sdk_wheel.name)
    print(f"Validation passed. Verified artifacts and reports: {output}", flush=True)


if __name__ == "__main__":
    main()
