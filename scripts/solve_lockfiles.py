from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.lockfiles import DEFAULT_PYTHON_PLATFORM, solve_lockfiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate install lockfiles and constraints for a bundle."
    )
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument(
        "--python-platform",
        default=DEFAULT_PYTHON_PLATFORM,
        help=(
            "Override the target platform for uv resolution. Defaults to the "
            "canonical platform used by policyengine-bundles."
        ),
    )
    args = parser.parse_args()
    solve_lockfiles(
        args.bundle_dir,
        python_platform=args.python_platform,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
