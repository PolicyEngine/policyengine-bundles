from __future__ import annotations

import json
from pathlib import Path

from policyengine_bundles.reproducibility import compare_bundle_directories


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def write_json(path: Path, payload: dict) -> None:
    write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def seed_bundle(root: Path, *, version: str = "1.0.0") -> None:
    write_json(
        root / "bundle.json",
        {
            "schema_version": 2,
            "bundle_version": version,
            "created_at": "2026-05-09T00:00:00Z",
            "bundle_digest": "sha256:" + "1" * 64,
            "policyengine": {
                "name": "policyengine",
                "version": version,
                "resolution_status": "pinned",
                "role": "bundle_carrier",
            },
            "packages": {
                "policyengine": {
                    "name": "policyengine",
                    "version": version,
                    "resolution_status": "pinned",
                    "role": "bundle_carrier",
                }
            },
            "countries": {"us": "countries/us.json"},
            "validation_report": "validation-report.json",
        },
    )
    write_json(
        root / "countries" / "us.json",
        {
            "schema_version": 2,
            "country_id": "us",
            "bundle_version": version,
            "value": "same",
        },
    )
    write_json(
        root / "validation-report.json",
        {
            "schema_version": 2,
            "bundle_version": version,
            "generated_at": "2026-05-09T00:00:00Z",
            "status": "passed",
            "metadata": {"validation_kind": "registry"},
            "checks": [
                {
                    "name": "bundle_directory_contract",
                    "status": "passed",
                    "details": {"bundle_dir": str(root)},
                }
            ],
        },
    )


def test_compare_bundle_directories_ignores_run_local_fields(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    seed_bundle(expected)
    seed_bundle(actual)

    bundle_payload = json.loads((actual / "bundle.json").read_text())
    bundle_payload["created_at"] = "2026-05-09T00:01:00Z"
    bundle_payload["bundle_digest"] = "sha256:" + "2" * 64
    write_json(actual / "bundle.json", bundle_payload)

    report_payload = json.loads((actual / "validation-report.json").read_text())
    report_payload["generated_at"] = "2026-05-09T00:01:00Z"
    write_json(actual / "validation-report.json", report_payload)

    assert compare_bundle_directories(expected, actual) == []


def test_compare_bundle_directories_reports_country_content_mismatch(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    seed_bundle(expected)
    seed_bundle(actual)
    country = json.loads((actual / "countries" / "us.json").read_text())
    country["value"] = "changed"
    write_json(actual / "countries" / "us.json", country)

    mismatches = compare_bundle_directories(expected, actual)

    assert len(mismatches) == 1
    assert "countries/us.json differs" in mismatches[0]
