from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import write_json

from policyengine_bundles.bundle_validation import validate_bundle
from policyengine_bundles.release import package_bundle_release
from policyengine_bundles.validation import load_bundle_directory

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_BUNDLES_ROOT = REPO_ROOT / "bundles"
LEGACY_BUNDLE_COUNTRIES = {
    "4.3.1": {"uk", "us"},
    "4.4.2": {"uk", "us"},
    "4.4.3": {"uk", "us"},
    "4.4.4": {"uk", "us"},
    "4.14.0": {"us"},
}


@pytest.mark.parametrize("version", LEGACY_BUNDLE_COUNTRIES)
def test_committed_legacy_bundle_loads_read_only(version: str) -> None:
    bundle = load_bundle_directory(LEGACY_BUNDLES_ROOT / version)

    assert bundle.manifest.schema_version == 1
    assert bundle.manifest.bundle_version == version
    assert set(bundle.countries) == LEGACY_BUNDLE_COUNTRIES[version]


def test_validate_bundle_rejects_legacy_bundle_without_writing_report() -> None:
    bundle_dir = LEGACY_BUNDLES_ROOT / "4.4.2"
    report_path = bundle_dir / "validation-report.json"
    original_report = report_path.read_text()

    with pytest.raises(ValueError, match="read-only historical bundle"):
        validate_bundle(bundle_dir)

    assert report_path.read_text() == original_report


def test_package_bundle_release_rejects_legacy_bundle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="read-only historical artifacts"):
        package_bundle_release(LEGACY_BUNDLES_ROOT / "4.4.2", tmp_path / "dist")


def test_legacy_bundle_rejects_unsafe_country_manifest_path(
    tmp_path: Path,
) -> None:
    bundle_dir = copy_legacy_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["countries"]["us"] = "../countries/us.json"
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="bundle-relative POSIX path"):
        load_bundle_directory(bundle_dir)


def test_legacy_bundle_rejects_country_version_drift(tmp_path: Path) -> None:
    bundle_dir = copy_legacy_bundle(tmp_path)
    country_json = bundle_dir / "countries" / "us.json"
    payload = json.loads(country_json.read_text())
    payload["bundle_version"] = "4.4.1"
    write_json(country_json, payload)

    with pytest.raises(ValueError, match="Legacy country 'us' bundle_version"):
        load_bundle_directory(bundle_dir)


def test_legacy_bundle_rejects_validation_report_version_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = copy_legacy_bundle(tmp_path)
    report_json = bundle_dir / "validation-report.json"
    payload = json.loads(report_json.read_text())
    payload["bundle_version"] = "4.4.1"
    write_json(report_json, payload)

    with pytest.raises(ValueError, match="Legacy validation report bundle_version"):
        load_bundle_directory(bundle_dir)


def test_legacy_bundle_rejects_profile_package_drift(tmp_path: Path) -> None:
    bundle_dir = copy_legacy_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["profiles"]["all"]["packages"].append("policyengine-ca")
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="references unknown packages"):
        load_bundle_directory(bundle_dir)


def test_legacy_bundle_rejects_profile_country_drift(tmp_path: Path) -> None:
    bundle_dir = copy_legacy_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["profiles"]["all"]["countries"].append("ca")
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="references unknown countries"):
        load_bundle_directory(bundle_dir)


def copy_legacy_bundle(tmp_path: Path) -> Path:
    output_dir = tmp_path / "4.4.2"
    shutil.copytree(LEGACY_BUNDLES_ROOT / "4.4.2", output_dir)
    return output_dir
