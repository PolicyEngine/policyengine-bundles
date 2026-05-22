from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[[Sequence[str]], CommandResult]


def run_command(command: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        list(command),
        check=False,
        text=True,
        capture_output=True,
    )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def publish_bundle_release_assets(
    *,
    version: str,
    dist_dir: Path | str,
    target_sha: str,
    repo: str | None = None,
    runner: CommandRunner = run_command,
) -> None:
    """Publish release assets for a new immutable bundle release."""

    tag = f"v{version}"
    assets = _release_assets(Path(dist_dir))
    _ensure_release_does_not_exist(tag=tag, repo=repo, runner=runner)
    command = _with_repo(
        [
            "gh",
            "release",
            "create",
            tag,
            *[str(asset) for asset in assets],
            "--target",
            target_sha,
            "--title",
            f"PolicyEngine bundle {version}",
            "--notes",
            (
                f"Immutable pre-release assets for PolicyEngine bundle {version}. "
                "The matching policyengine.py wheel hash is attested after "
                "policyengine.py publishes."
            ),
            "--prerelease",
        ],
        repo,
    )
    result = runner(command)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to create GitHub release {tag}: {result.stderr or result.stdout}"
        )


def _release_assets(dist_dir: Path) -> list[Path]:
    assets = sorted(path for path in dist_dir.iterdir() if path.is_file())
    if not assets:
        raise ValueError(f"No release assets found in {dist_dir}.")
    return assets


def _ensure_release_does_not_exist(
    *,
    tag: str,
    repo: str | None,
    runner: CommandRunner,
) -> None:
    result = runner(
        _with_repo(
            [
                "gh",
                "release",
                "view",
                tag,
                "--json",
                "tagName,targetCommitish",
            ],
            repo,
        )
    )
    if result.returncode == 0:
        raise ValueError(
            f"Release {tag} already exists. Refusing to modify an existing "
            "immutable bundle release."
        )
    output = f"{result.stdout}\n{result.stderr}".lower()
    if "not found" not in output:
        raise RuntimeError(
            f"Could not determine whether release {tag} exists: "
            f"{result.stderr or result.stdout}"
        )


def _with_repo(command: list[str], repo: str | None) -> list[str]:
    if repo is None:
        return command
    return [*command, "--repo", repo]
