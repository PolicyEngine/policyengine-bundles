from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from conftest import write_json
from test_package_bundle_release import certified_bundle

from policyengine_bundles.release import package_bundle_release, release_asset_names


def _load_check_existing_bundle_release() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_existing_bundle_release.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_existing_bundle_release",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_existing_bundle_release = _load_check_existing_bundle_release()


def _fake_existing_release(
    monkeypatch: pytest.MonkeyPatch,
    *,
    version: str,
    existing_dist: Path,
) -> None:
    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "release", "view"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ["gh", "release", "download"]:
            asset_name = command[command.index("--pattern") + 1]
            output_dir = Path(command[command.index("--dir") + 1])
            assert asset_name in release_asset_names(version)
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(existing_dist / asset_name, output_dir / asset_name)
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(check_existing_bundle_release, "run", fake_run)


def _fake_release_view_failure(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stderr: str,
) -> None:
    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "release", "view"]:
            return subprocess.CompletedProcess(command, 1, "", stderr)
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(check_existing_bundle_release, "run", fake_run)


def _run_script(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tmp_path: Path,
    version: str,
    dist_dir: Path,
) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_existing_bundle_release.py",
            "--bundle-version",
            version,
            "--dist-dir",
            str(dist_dir),
            "--repo",
            "PolicyEngine/policyengine-bundles",
            "--existing-release-dir",
            str(tmp_path / "existing-release"),
        ],
    )
    return check_existing_bundle_release.main()


def test_check_existing_bundle_release_accepts_matching_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = "4.4.0"
    existing_bundle = certified_bundle(tmp_path / "bundle")
    committed_bundle = tmp_path / "committed" / version
    shutil.copytree(existing_bundle, committed_bundle)

    existing_dist = tmp_path / "existing-dist"
    committed_dist = tmp_path / "committed-dist"
    package_bundle_release(existing_bundle, existing_dist)
    package_bundle_release(committed_bundle, committed_dist)
    _fake_existing_release(
        monkeypatch,
        version=version,
        existing_dist=existing_dist,
    )

    assert (
        _run_script(
            monkeypatch,
            tmp_path=tmp_path,
            version=version,
            dist_dir=committed_dist,
        )
        == 0
    )


def test_check_existing_bundle_release_rejects_real_content_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = "4.4.0"
    existing_bundle = certified_bundle(tmp_path / "bundle")
    committed_bundle = tmp_path / "committed" / version
    shutil.copytree(existing_bundle, committed_bundle)
    country_path = committed_bundle / "countries" / "us.json"
    country = json.loads(country_path.read_text())
    country["datasets"]["enhanced_cps_2024"]["size_bytes"] = 13
    write_json(country_path, country)

    existing_dist = tmp_path / "existing-dist"
    committed_dist = tmp_path / "committed-dist"
    package_bundle_release(existing_bundle, existing_dist)
    package_bundle_release(committed_bundle, committed_dist)
    _fake_existing_release(
        monkeypatch,
        version=version,
        existing_dist=existing_dist,
    )

    with pytest.raises(SystemExit, match="does not match committed bundle"):
        _run_script(
            monkeypatch,
            tmp_path=tmp_path,
            version=version,
            dist_dir=committed_dist,
        )


def test_check_existing_bundle_release_accepts_missing_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_release_view_failure(monkeypatch, stderr="release not found")

    assert (
        _run_script(
            monkeypatch,
            tmp_path=tmp_path,
            version="4.4.0",
            dist_dir=tmp_path / "dist",
        )
        == 0
    )


def test_check_existing_bundle_release_rejects_ambiguous_view_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_release_view_failure(monkeypatch, stderr="HTTP 401: Bad credentials")

    with pytest.raises(RuntimeError, match="Bad credentials"):
        _run_script(
            monkeypatch,
            tmp_path=tmp_path,
            version="4.4.0",
            dist_dir=tmp_path / "dist",
        )
