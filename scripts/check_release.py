"""Require the dispatched Git ref to match the package's exact version tag."""

import argparse
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="Full Git ref, such as refs/tags/v0.4.1")
    parser.add_argument(
        "--repository", choices=("testpypi", "pypi"), default="testpypi"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    expected = f"refs/tags/v{version}"
    if args.ref != expected:
        parser.error(f"Publishing requires {expected}; got {args.ref}")
    print(f"Release ref matches project.version: {expected}")


if __name__ == "__main__":
    main()
