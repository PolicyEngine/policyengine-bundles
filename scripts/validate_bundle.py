from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.bundle_validation import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a complete generated PolicyEngine bundle."
    )
    parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    report = validate_bundle(
        args.bundle_dir,
    )
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
