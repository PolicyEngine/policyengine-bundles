from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from policyengine_bundles.release import (
    release_asset_names,
    verify_and_unpack_bundle_release,
)
from policyengine_bundles.reproducibility import compare_bundle_directories


def write_output(name: str, value: str) -> None:
    line = f"{name}={value}\n"
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as output:
            output.write(line)
    else:
        print(line, end="")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check whether a matching bundle release already exists."
    )
    parser.add_argument("--bundle-version", required=True)
    parser.add_argument("--dist-dir", required=True, type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--existing-release-dir",
        default=Path(".tmp/existing-release"),
        type=Path,
    )
    args = parser.parse_args()

    version = args.bundle_version
    view = run(["gh", "release", "view", f"v{version}", "--repo", args.repo])
    if view.returncode != 0:
        if not _release_not_found(view):
            raise RuntimeError(view.stderr or view.stdout)
        write_output("exists", "false")
        return 0

    write_output("exists", "true")
    args.existing_release_dir.mkdir(parents=True, exist_ok=True)
    for asset_name in release_asset_names(version):
        asset_path = args.existing_release_dir / asset_name
        if asset_path.exists():
            asset_path.unlink()
        download = run(
            [
                "gh",
                "release",
                "download",
                f"v{version}",
                "--repo",
                args.repo,
                "--pattern",
                asset_name,
                "--dir",
                str(args.existing_release_dir),
            ]
        )
        if download.returncode != 0:
            raise RuntimeError(download.stderr or download.stdout)

    with TemporaryDirectory() as temp_dir:
        unpacked = Path(temp_dir)
        committed_bundle = verify_and_unpack_bundle_release(
            version=version,
            dist_dir=args.dist_dir,
            output_dir=unpacked / "committed",
        )
        existing_bundle = verify_and_unpack_bundle_release(
            version=version,
            dist_dir=args.existing_release_dir,
            output_dir=unpacked / "existing",
        )
        mismatches = compare_bundle_directories(existing_bundle, committed_bundle)

    if mismatches:
        raise SystemExit(
            f"Existing release v{version} does not match committed bundle.\n"
            + "\n\n".join(mismatches)
        )

    print(f"existing release v{version} matches committed bundle")
    return 0


def _release_not_found(result: subprocess.CompletedProcess[str]) -> bool:
    output = f"{result.stderr}\n{result.stdout}".lower()
    return "not found" in output or "http 404" in output


if __name__ == "__main__":
    raise SystemExit(main())
