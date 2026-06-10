from __future__ import annotations

import argparse
import json
import os
import tarfile
from pathlib import Path
from typing import Any

REQUIRED_POLICYENGINE_PY_IMPORT_PACKAGES = ("policyengine-uk", "policyengine-us")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Decide whether a published bundle can be imported automatically "
            "into policyengine.py."
        )
    )
    parser.add_argument("bundle_version")
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()

    bundle = load_release_bundle_manifest(
        version=args.bundle_version,
        dist_dir=args.dist_dir,
    )
    should_open, reason = should_open_policyengine_py_consuming_pr(bundle)
    print(reason)
    write_github_output(
        should_open=should_open,
        reason=reason,
    )
    return 0


def load_release_bundle_manifest(*, version: str, dist_dir: Path) -> dict[str, Any]:
    archive_path = dist_dir / f"policyengine-bundle-{version}.tar.gz"
    member_name = f"policyengine-bundle-{version}/bundle.json"
    with tarfile.open(archive_path) as archive:
        member = archive.extractfile(member_name)
        if member is None:
            raise FileNotFoundError(f"{member_name} missing from {archive_path}")
        return json.load(member)


def should_open_policyengine_py_consuming_pr(
    bundle: dict[str, Any],
) -> tuple[bool, str]:
    bundle_version = bundle.get("bundle_version", "unknown")
    schema_version = bundle.get("schema_version")
    if schema_version != 2:
        return (
            False,
            f"Skipping policyengine.py consuming PR for bundle {bundle_version}: "
            "automated importer supports bundle schema v2 only; "
            f"got schema_version={schema_version!r}.",
        )

    packages = bundle.get("packages")
    if not isinstance(packages, dict):
        raise TypeError("bundle packages must be an object")

    missing = [
        package
        for package in REQUIRED_POLICYENGINE_PY_IMPORT_PACKAGES
        if package not in packages
    ]
    if missing:
        missing_text = ", ".join(missing)
        return (
            False,
            f"Skipping policyengine.py consuming PR for bundle {bundle_version}: "
            f"automated importer requires {missing_text}.",
        )
    return (
        True,
        f"Bundle {bundle_version} has all packages needed for policyengine.py import.",
    )


def write_github_output(*, should_open: bool, reason: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a") as output:
        output.write(f"should_open={str(should_open).lower()}\n")
        output.write(f"reason={reason}\n")


if __name__ == "__main__":
    raise SystemExit(main())
