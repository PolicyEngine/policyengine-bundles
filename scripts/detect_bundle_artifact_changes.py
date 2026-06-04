from __future__ import annotations

import os
import subprocess

ZERO_SHA = "0000000000000000000000000000000000000000"


def write_output(name: str, value: str) -> None:
    line = f"{name}={value}\n"
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as output:
            output.write(line)
    else:
        print(line, end="")


def changed_paths(base_sha: str, head_sha: str) -> list[str]:
    if not base_sha or base_sha == ZERO_SHA:
        command = [
            "git",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            head_sha,
        ]
    else:
        command = ["git", "diff", "--name-only", base_sha, head_sha]
    return subprocess.check_output(command, text=True).splitlines()


def has_bundle_artifact_changes(paths: list[str]) -> bool:
    return any(path.startswith(("bundles/", "candidates/")) for path in paths)


def main() -> int:
    if os.environ["EVENT_NAME"] == "workflow_dispatch":
        write_output("changed", "true")
        return 0

    changed = has_bundle_artifact_changes(
        changed_paths(
            base_sha=os.environ.get("BASE_SHA", ""),
            head_sha=os.environ["HEAD_SHA"],
        )
    )
    write_output("changed", str(changed).lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
