from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.bundle_validation import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a complete generated PolicyEngine bundle."
    )
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument(
        "--skip-data-verification",
        action="store_true",
        help=(
            "Skip release manifest and data artifact hash/reachability checks. "
            "The generated report is partial and is not certification evidence."
        ),
    )
    parser.add_argument(
        "--skip-runtime-validation",
        action="store_true",
        help=(
            "Skip lockfile, constraints, environment creation, import, and "
            "household smoke checks. The generated report is partial and is not "
            "certification evidence."
        ),
    )
    args = parser.parse_args()
    report = validate_bundle(
        args.bundle_dir,
        verify_data=not args.skip_data_verification,
        validate_runtime=not args.skip_runtime_validation,
    )
    return 1 if any(check.status == "failed" for check in report.checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
