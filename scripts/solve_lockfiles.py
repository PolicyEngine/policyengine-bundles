from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.lockfiles import DEFAULT_PYTHON_PLATFORMS, solve_lockfiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate install lockfiles and constraints for a bundle."
    )
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument(
        "--python-version",
        action="append",
        dest="python_versions",
        help=(
            "Python version to solve, for example 3.13. May be repeated. "
            "Defaults to bundle.json metadata.python_versions."
        ),
    )
    parser.add_argument(
        "--python-platform",
        action="append",
        dest="python_platforms",
        help=(
            "uv target platform for generated constraints and lockfiles. "
            "May be repeated. Defaults to "
            f"{', '.join(DEFAULT_PYTHON_PLATFORMS)}."
        ),
    )
    args = parser.parse_args()
    solve_lockfiles(
        args.bundle_dir,
        python_versions=args.python_versions,
        python_platforms=args.python_platforms,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
