from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.lockfiles import solve_lockfiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate install lockfiles and constraints for a bundle."
    )
    parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    solve_lockfiles(
        args.bundle_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
