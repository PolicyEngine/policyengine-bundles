from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


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
        write_output("exists", "false")
        return 0

    write_output("exists", "true")
    args.existing_release_dir.mkdir(parents=True, exist_ok=True)
    asset_name = f"policyengine-bundle-{version}.json"
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

    expected = json.loads((args.dist_dir / asset_name).read_text())
    actual = json.loads((args.existing_release_dir / asset_name).read_text())
    if expected != actual:
        raise SystemExit(
            f"Existing release v{version} does not match committed bundle."
        )
    print(f"existing release v{version} matches committed bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
