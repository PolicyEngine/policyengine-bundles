from __future__ import annotations

import argparse
import json
from pathlib import Path

from policyengine_bundles.bundle_validation import validate_bundle
from policyengine_bundles.generation import generate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and validate a registry bundle from a candidate."
    )
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    generate_bundle(args.candidate, args.output)
    report = validate_bundle(args.output)
    failed_checks = [check for check in report.checks if check.status == "failed"]
    if failed_checks:
        print("Failed validation checks:")
        for check in failed_checks:
            print(json.dumps(check.model_dump(exclude_none=True), indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
