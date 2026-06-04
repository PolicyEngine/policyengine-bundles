from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.release import (
    DEFAULT_RELEASE_BASE_URL,
    fetch_bundle_release,
    verify_and_unpack_bundle_release,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch or verify a published PolicyEngine bundle release."
    )
    parser.add_argument("version")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist/fetched-bundles"),
        help="Directory where the verified bundle archive is unpacked.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_RELEASE_BASE_URL,
        help="Base release URL. Defaults to PolicyEngine bundle GitHub releases.",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help=(
            "Verify already-downloaded release assets from this directory instead "
            "of downloading them."
        ),
    )
    args = parser.parse_args()

    if args.dist_dir is not None:
        bundle_dir = verify_and_unpack_bundle_release(
            version=args.version,
            dist_dir=args.dist_dir,
            output_dir=args.output_dir,
        )
    else:
        bundle_dir = fetch_bundle_release(
            version=args.version,
            output_dir=args.output_dir,
            base_url=args.base_url,
        )

    print(f"verified bundle: {bundle_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
