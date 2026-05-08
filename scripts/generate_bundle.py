from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.generation import generate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a PolicyEngine bundle from an explicit candidate spec."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing non-empty output directory.",
    )
    args = parser.parse_args()
    generate_bundle(args.input, args.output, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
