from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ZERO_SHA = "0000000000000000000000000000000000000000"


def version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise SystemExit(f"Invalid bundle version {version!r}.") from exc


def write_output(name: str, value: str) -> None:
    line = f"{name}={value}\n"
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as output:
            output.write(line)
    else:
        print(line, end="")


def changed_paths(before: str, after: str) -> list[str]:
    if before == ZERO_SHA:
        command = [
            "git",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            after,
        ]
    else:
        command = ["git", "diff", "--name-only", before, after]
    return subprocess.check_output(command, text=True).splitlines()


def load_candidate(path: Path) -> dict:
    return json.loads(path.read_text())


def is_active_candidate(path: Path) -> bool:
    return load_candidate(path).get("schema_version") == 2


def latest_candidate_version() -> str:
    candidates = []
    for path in Path("candidates").glob("*.json"):
        if not is_active_candidate(path):
            continue
        payload = load_candidate(path)
        version = payload["bundle_version"]
        candidates.append((version_key(version), version))
    if not candidates:
        raise SystemExit("No active schema v2 bundle candidates found.")
    return max(candidates)[1]


def changed_bundle_versions(paths: list[str]) -> set[str]:
    versions: set[str] = set()
    for changed_path in paths:
        parts = Path(changed_path).parts
        if len(parts) >= 2 and parts[0] == "candidates" and parts[1].endswith(".json"):
            path = Path(changed_path)
            if path.exists() and is_active_candidate(path):
                payload = load_candidate(path)
                versions.add(payload["bundle_version"])
    return versions


def selected_versions() -> set[str]:
    requested = os.environ.get("REQUESTED_BUNDLE_VERSION", "").strip()
    if requested:
        return {requested}
    if os.environ["EVENT_NAME"] == "workflow_dispatch":
        return {latest_candidate_version()}
    return changed_bundle_versions(
        changed_paths(
            before=os.environ["BEFORE_SHA"],
            after=os.environ["AFTER_SHA"],
        )
    )


def main() -> int:
    versions = selected_versions()
    if not versions:
        write_output("should_publish", "false")
        write_output("reason", "No candidate changes found in this push.")
        return 0

    ordered_versions = sorted(versions, key=version_key)
    if len(ordered_versions) != 1:
        raise SystemExit(
            "Expected exactly one bundle version per publication push; got "
            + ", ".join(ordered_versions)
        )

    version = ordered_versions[0]
    candidate_path = candidate_path_for_version(version)
    if not candidate_path.exists():
        raise SystemExit(f"Committed candidate missing: {candidate_path}")

    write_output("should_publish", "true")
    write_output("bundle_version", version)
    write_output("candidate", candidate_path.as_posix())
    write_output("generated_bundle", f".tmp/generated-bundles/{version}")
    return 0


def candidate_path_for_version(version: str) -> Path:
    matches = []
    for path in Path("candidates").glob("*.json"):
        if not is_active_candidate(path):
            continue
        payload = load_candidate(path)
        if payload["bundle_version"] == version:
            matches.append(path)
    if not matches:
        raise SystemExit(
            f"Committed active schema v2 candidate missing for bundle {version}."
        )
    if len(matches) > 1:
        raise SystemExit(
            "Expected exactly one candidate for bundle "
            f"{version}; got {', '.join(path.as_posix() for path in matches)}."
        )
    return matches[0]


if __name__ == "__main__":
    raise SystemExit(main())
