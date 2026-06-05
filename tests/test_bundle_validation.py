from __future__ import annotations

import json
from pathlib import Path

from conftest import generated_bundle, write_json

from policyengine_bundles.bundle_validation import validate_bundle
from policyengine_bundles.models import ValidationReport


def report_has_failed_check(
    report: ValidationReport,
    check_name: str,
    failure_fragment: str,
) -> bool:
    return any(
        check.name == check_name
        and check.status == "failed"
        and any(
            failure_fragment in failure for failure in check.details.get("failures", [])
        )
        for check in report.checks
    )


def test_validate_bundle_runs_registry_checks(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")

    report = validate_bundle(bundle_dir)

    assert report.schema_version == 2
    assert report.status == "passed"
    assert report.metadata["validation_kind"] == "registry"
    check_names = {check.name for check in report.checks}
    assert check_names == {
        "bundle_directory_contract",
        "package_pin",
        "compatibility_assertion",
        "release_manifest_provenance",
        "default_dataset",
        "data_artifact_metadata",
    }
    persisted_report = json.loads((bundle_dir / "validation-report.json").read_text())
    assert persisted_report["status"] == "passed"


def test_validate_bundle_fails_missing_package_sha(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["packages"]["policyengine-us"].pop("sha256")
    write_json(bundle_json, payload)
    country_json = bundle_dir / "countries" / "us.json"
    country_payload = json.loads(country_json.read_text())
    country_payload["model_package"].pop("sha256")
    country_payload["compatibility"]["model_package"].pop("sha256")
    write_json(country_json, country_payload)

    report = validate_bundle(bundle_dir)

    assert report.status == "failed"
    assert report_has_failed_check(report, "package_pin", "wheel sha256")


def test_validate_bundle_fails_when_default_dataset_missing(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    country_json = bundle_dir / "countries" / "us.json"
    payload = json.loads(country_json.read_text())
    payload["default_dataset"] = "missing"
    write_json(country_json, payload)

    report = validate_bundle(bundle_dir)

    assert report.status == "failed"
    assert report_has_failed_check(
        report,
        "default_dataset",
        "default_dataset",
    )


def test_validate_bundle_reports_load_failure_for_invalid_artifact_metadata(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, validate=False, output_name="bundle")
    country_json = bundle_dir / "countries" / "us.json"
    payload = json.loads(country_json.read_text())
    payload["datasets"]["enhanced_cps_2024"].pop("sha256")
    write_json(country_json, payload)

    report = validate_bundle(bundle_dir)

    assert report.status == "failed"
    assert any(
        check.name == "bundle_directory_contract" and check.status == "failed"
        for check in report.checks
    )


def test_validate_bundle_reports_bundle_load_failure(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    write_json(bundle_dir / "bundle.json", {"bundle_version": "4.4.0"})

    report = validate_bundle(bundle_dir)

    assert report.status == "failed"
    assert report.checks[0].name == "bundle_directory_contract"
    assert (bundle_dir / "validation-report.json").exists()
