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
    parser.add_argument(
        "--testing-only",
        action="store_true",
        help="Allow local file release manifests without embedding them.",
    )
    parser.add_argument(
        "--embed-local-manifests",
        action="store_true",
        help=(
            "Copy local file release manifests into source-manifests/<country>/ "
            "and reference those stable relative paths."
        ),
    )
    args = parser.parse_args()
    generate_bundle(
        args.input,
        args.output,
        force=args.force,
        testing_only=args.testing_only,
        embed_local_manifests=args.embed_local_manifests,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
