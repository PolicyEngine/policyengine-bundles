from __future__ import annotations

import argparse
from pathlib import Path

from policyengine_bundles.bundle_validation import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a generated PolicyEngine bundle runtime profile."
    )
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("--profile", action="append", dest="profiles")
    parser.add_argument("--python-version", action="append", dest="python_versions")
    parser.add_argument(
        "--python-platform",
        action="append",
        dest="python_platforms",
        help=(
            "Python platform install target to validate, for example linux, macos, "
            "or windows. May be repeated. Defaults to the current runner platform."
        ),
    )
    args = parser.parse_args()
    report = validate_bundle(
        args.bundle_dir,
        profiles=args.profiles,
        python_versions=args.python_versions,
        python_platforms=args.python_platforms,
    )
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
