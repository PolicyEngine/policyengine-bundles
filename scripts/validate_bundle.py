from __future__ import annotations

import argparse
import json
from pathlib import Path

from policyengine_bundles.bundle_validation import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a generated PolicyEngine registry bundle."
    )
    parser.add_argument("bundle_dir", type=Path)
    args = parser.parse_args()
    report = validate_bundle(args.bundle_dir)
    failed_checks = [check for check in report.checks if check.status == "failed"]
    if failed_checks:
        print("Failed validation checks:")
        for check in failed_checks:
            print(json.dumps(check.model_dump(exclude_none=True), indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
