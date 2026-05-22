from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.digest import verify_bundle_digests


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify committed bundle_digest values under bundles/."
    )
    parser.add_argument(
        "bundles_root",
        nargs="?",
        type=Path,
        default=Path("bundles"),
    )
    args = parser.parse_args()

    failures = verify_bundle_digests(args.bundles_root)
    if failures:
        print("\n".join(failures))
        return 1
    print(f"bundle digests ok: {args.bundles_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
