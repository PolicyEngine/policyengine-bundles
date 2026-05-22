from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.release import package_bundle_release


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create immutable release artifacts for a certified bundle."
    )
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="Directory for release artifacts.",
    )
    args = parser.parse_args()

    archive_path, checksum_path = package_bundle_release(
        args.bundle_dir,
        args.output_dir,
    )
    print(f"created {archive_path}")
    print(f"created {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
