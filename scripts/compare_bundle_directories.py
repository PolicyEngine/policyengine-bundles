from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.reproducibility import compare_bundle_directories


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a checked-in bundle with a regenerated bundle, ignoring "
            "run-local timestamps, temp paths, and resolver comments."
        )
    )
    parser.add_argument("expected_bundle_dir", type=Path)
    parser.add_argument("regenerated_bundle_dir", type=Path)
    args = parser.parse_args()

    mismatches = compare_bundle_directories(
        args.expected_bundle_dir,
        args.regenerated_bundle_dir,
    )
    if mismatches:
        print("\n\n".join(mismatches))
        return 1

    print(
        "bundle comparison ok: "
        f"{args.expected_bundle_dir} matches {args.regenerated_bundle_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
