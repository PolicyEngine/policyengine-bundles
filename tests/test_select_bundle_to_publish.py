from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "select_bundle_to_publish.py"
)
SPEC = importlib.util.spec_from_file_location("select_bundle_to_publish", SCRIPT_PATH)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
candidate_path_for_version = MODULE.candidate_path_for_version
changed_bundle_versions = MODULE.changed_bundle_versions
latest_candidate_version = MODULE.latest_candidate_version


def test_latest_candidate_version_ignores_higher_legacy_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_candidate(tmp_path / "candidates" / "9.0.0-legacy.json", legacy_candidate())
    write_candidate(tmp_path / "candidates" / "4.15.0-current.json", active_candidate())
    monkeypatch.chdir(tmp_path)

    assert latest_candidate_version() == "4.15.0"


def test_changed_bundle_versions_ignores_legacy_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_candidate(tmp_path / "candidates" / "9.0.0-legacy.json", legacy_candidate())
    write_candidate(tmp_path / "candidates" / "4.15.0-current.json", active_candidate())
    monkeypatch.chdir(tmp_path)

    versions = changed_bundle_versions(
        [
            "candidates/9.0.0-legacy.json",
            "candidates/4.15.0-current.json",
        ]
    )

    assert versions == {"4.15.0"}


def test_candidate_path_for_version_requires_active_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_candidate(tmp_path / "candidates" / "9.0.0-legacy.json", legacy_candidate())
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit, match="active schema v2 candidate missing"):
        candidate_path_for_version("9.0.0")


def write_candidate(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def legacy_candidate() -> dict:
    return {
        "schema_version": 1,
        "bundle_version": "9.0.0",
        "policyengine_version": "9.0.0",
        "python_versions": ["3.13"],
        "profiles": ["us"],
        "packages": {
            "policyengine-core": "3.26.1",
            "policyengine-us": "1.715.3",
        },
        "countries": {
            "us": {
                "model_package": "policyengine-us",
                "data_release_manifest_uri": (
                    "hf://model/policyengine/policyengine-us-data@1.0.0/"
                    "release_manifest.json"
                ),
            },
        },
    }


def active_candidate() -> dict:
    return {
        "schema_version": 2,
        "bundle_version": "4.15.0",
        "packages": {
            "policyengine-core": "3.26.1",
            "policyengine-us": "1.715.3",
        },
        "countries": {
            "us": {
                "model_package": "policyengine-us",
                "data_release_manifest_uri": (
                    "hf://model/policyengine/policyengine-us-data@1.0.0/"
                    "release_manifest.json"
                ),
            },
        },
    }
