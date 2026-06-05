from __future__ import annotations

import json
import os
from pathlib import Path


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def write_output(name: str, value: str) -> None:
    line = f"{name}={value}\n"
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as output:
            output.write(line)
    else:
        print(line, end="")


def main() -> int:
    candidates = []
    for path in Path("candidates").glob("*.json"):
        payload = json.loads(path.read_text())
        version = payload["bundle_version"]
        candidates.append((version_key(version), version, path))

    if not candidates:
        raise SystemExit("No bundle candidates found.")

    _, version, path = max(candidates)
    write_output("bundle_version", version)
    write_output("candidate", path.as_posix())
    write_output("output", f".tmp/bundle-{version}")
    write_output("committed", f"bundles/{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
