from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.lockfiles import solve_lockfiles


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
    args = parser.parse_args()
    solve_lockfiles(
        args.bundle_dir,
        python_versions=args.python_versions,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
