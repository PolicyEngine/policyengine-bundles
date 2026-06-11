from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import generated_bundle, write_json

from policyengine_bundles.validation import load_bundle_directory


def test_load_bundle_directory_rejects_country_package_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    country_json = bundle_dir / "countries" / "us.json"
    payload = json.loads(country_json.read_text())
    payload["core_package"]["version"] = "3.27.0"
    write_json(country_json, payload)

    with pytest.raises(ValueError, match="does not match bundle.json packages entry"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_compatibility_model_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    country_json = bundle_dir / "countries" / "us.json"
    payload = json.loads(country_json.read_text())
    payload["compatibility"]["model_package"]["version"] = "1.0.1"
    write_json(country_json, payload)

    with pytest.raises(ValueError, match="compatibility model_package"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_compatibility_data_package_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    country_json = bundle_dir / "countries" / "us.json"
    payload = json.loads(country_json.read_text())
    payload["compatibility"]["data_package"]["version"] = "1.0.1"
    write_json(country_json, payload)

    with pytest.raises(ValueError, match="compatibility data_package"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_report_version_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    report_json = bundle_dir / "validation-report.json"
    payload = json.loads(report_json.read_text())
    payload["bundle_version"] = "4.4.1"
    write_json(report_json, payload)

    with pytest.raises(ValueError, match="Validation report bundle_version"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_policyengine_version_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["policyengine"]["version"] = "4.4.1"
    payload["packages"]["policyengine"]["version"] = "4.4.1"
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="does not match bundle_version"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_policyengine_package_pin_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["packages"]["policyengine"]["sha256"] = "d" * 64
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="policyengine pin must match"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_unsafe_country_manifest_path(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["countries"]["us"] = "../countries/us.json"
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="bundle-relative POSIX path"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_unsafe_validation_report_path(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["validation_report"] = "/tmp/validation-report.json"
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="bundle-relative POSIX path"):
        load_bundle_directory(bundle_dir)
