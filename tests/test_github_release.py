from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from policyengine_bundles.github_release import (
    CommandResult,
    publish_bundle_release_assets,
)


class FakeRunner:
    def __init__(self, view_result: CommandResult):
        self.view_result = view_result
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> CommandResult:
        command_list = list(command)
        self.commands.append(command_list)
        if command_list[:3] == ["gh", "release", "view"]:
            return self.view_result
        return CommandResult(returncode=0)


def write_asset(path: Path, content: str = "asset") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_publish_bundle_release_assets_creates_release_from_target_sha(
    tmp_path: Path,
) -> None:
    write_asset(tmp_path / "dist/b.txt")
    write_asset(tmp_path / "dist/a.txt")
    runner = FakeRunner(CommandResult(returncode=1, stderr="release not found"))

    publish_bundle_release_assets(
        version="4.4.2",
        dist_dir=tmp_path / "dist",
        target_sha="abc123",
        repo="PolicyEngine/policyengine-bundles",
        runner=runner,
    )

    assert runner.commands == [
        [
            "gh",
            "release",
            "view",
            "v4.4.2",
            "--json",
            "tagName,targetCommitish",
            "--repo",
            "PolicyEngine/policyengine-bundles",
        ],
        [
            "gh",
            "release",
            "create",
            "v4.4.2",
            str(tmp_path / "dist/a.txt"),
            str(tmp_path / "dist/b.txt"),
            "--target",
            "abc123",
            "--title",
            "PolicyEngine bundle 4.4.2",
            "--notes",
            (
                "Immutable pre-release assets for PolicyEngine bundle 4.4.2. "
                "The matching policyengine.py wheel hash is attested after "
                "policyengine.py publishes."
            ),
            "--prerelease",
            "--repo",
            "PolicyEngine/policyengine-bundles",
        ],
    ]


def test_publish_bundle_release_assets_refuses_existing_release(
    tmp_path: Path,
) -> None:
    write_asset(tmp_path / "dist/bundle.json")
    runner = FakeRunner(CommandResult(returncode=0, stdout='{"tagName":"v4.4.2"}'))

    with pytest.raises(ValueError, match="already exists"):
        publish_bundle_release_assets(
            version="4.4.2",
            dist_dir=tmp_path / "dist",
            target_sha="abc123",
            runner=runner,
        )


def test_publish_bundle_release_assets_fails_on_ambiguous_view_error(
    tmp_path: Path,
) -> None:
    write_asset(tmp_path / "dist/bundle.json")
    runner = FakeRunner(CommandResult(returncode=1, stderr="authentication failed"))

    with pytest.raises(RuntimeError, match="Could not determine"):
        publish_bundle_release_assets(
            version="4.4.2",
            dist_dir=tmp_path / "dist",
            target_sha="abc123",
            runner=runner,
        )


def test_publish_bundle_release_assets_requires_assets(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    runner = FakeRunner(CommandResult(returncode=1, stderr="release not found"))

    with pytest.raises(ValueError, match="No release assets"):
        publish_bundle_release_assets(
            version="4.4.2",
            dist_dir=tmp_path / "dist",
            target_sha="abc123",
            runner=runner,
        )
