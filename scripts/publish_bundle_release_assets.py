from __future__ import annotations

import argparse
import os
from pathlib import Path

from policyengine_bundles.github_release import publish_bundle_release_assets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a new immutable GitHub release for bundle assets."
    )
    parser.add_argument("version")
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Directory containing release assets.",
    )
    parser.add_argument(
        "--target-sha",
        default=os.environ.get("GITHUB_SHA"),
        help="Commit SHA for the release tag. Defaults to GITHUB_SHA.",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="GitHub repository in owner/name form. Defaults to GITHUB_REPOSITORY.",
    )
    args = parser.parse_args()
    if not args.target_sha:
        raise SystemExit("--target-sha is required outside GitHub Actions.")

    publish_bundle_release_assets(
        version=args.version,
        dist_dir=args.dist_dir,
        target_sha=args.target_sha,
        repo=args.repo,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
