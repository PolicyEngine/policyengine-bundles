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
            "schema_version": 1,
            "bundle_version": version,
            "created_at": "2026-05-09T00:00:00Z",
            "packages": {"policyengine": {"version": version}},
        },
    )
    write_json(
        root / "validation-report.json",
        {
            "schema_version": 1,
            "bundle_version": version,
            "generated_at": "2026-05-09T00:00:00Z",
            "status": "passed",
            "metadata": {
                "validation_scope": "full",
                "verify_data": True,
                "validate_runtime": True,
            },
            "checks": [
                {
                    "name": "verify_direct_package_versions",
                    "status": "passed",
                    "profile": "all",
                    "python_version": "3.13",
                    "command": "/tmp/tmpa/venv/bin/python -c '...'",
                    "started_at": "2026-05-09T00:00:00Z",
                    "ended_at": "2026-05-09T00:00:01Z",
                    "details": {"validated_on_platform": "linux"},
                }
            ],
        },
    )
    write(
        root / "install/all/py313/constraints.txt",
        "# generated from /tmp/tmpa/requirements.in\n"
        "policyengine==1.0.0 \\\n"
        "    --hash=sha256:abc\n"
        "    # via -r /tmp/tmpa/requirements.in\n",
    )
    write(
        root / "install/all/py313/pylock.toml",
        "# generated from /tmp/tmpa/requirements.in\n"
        'lock-version = "1.0"\n'
        'created-by = "uv"\n',
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
    write_json(actual / "bundle.json", bundle_payload)

    report_payload = json.loads((actual / "validation-report.json").read_text())
    report_payload["generated_at"] = "2026-05-09T00:01:00Z"
    report_payload["checks"][0]["command"] = "/tmp/tmpb/venv/bin/python -c '...'"
    report_payload["checks"][0]["started_at"] = "2026-05-09T00:01:00Z"
    report_payload["checks"][0]["ended_at"] = "2026-05-09T00:01:01Z"
    report_payload["checks"][0]["details"]["validated_on_platform"] = "macos"
    write_json(actual / "validation-report.json", report_payload)

    constraints = (actual / "install/all/py313/constraints.txt").read_text()
    constraints = constraints.replace("/tmp/tmpa", "/tmp/tmpb")
    write(actual / "install/all/py313/constraints.txt", constraints)
    pylock = (actual / "install/all/py313/pylock.toml").read_text()
    pylock = pylock.replace("/tmp/tmpa", "/tmp/tmpb")
    write(actual / "install/all/py313/pylock.toml", pylock)

    assert compare_bundle_directories(expected, actual) == []


def test_compare_bundle_directories_reports_lockfile_content_mismatch(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    seed_bundle(expected)
    seed_bundle(actual)
    write(
        actual / "install/all/py313/pylock.toml",
        "# generated from /tmp/tmpa/requirements.in\n"
        'lock-version = "1.0"\n'
        'created-by = "different"\n',
    )

    mismatches = compare_bundle_directories(expected, actual)

    assert len(mismatches) == 1
    assert "install/all/py313/pylock.toml differs" in mismatches[0]


def test_compare_bundle_directories_treats_legacy_validation_mode_as_default(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "expected"
    actual = tmp_path / "actual"
    seed_bundle(expected)
    seed_bundle(actual)

    expected_manifest = json.loads((expected / "bundle.json").read_text())
    expected_manifest["bundle_digest"] = "sha256:" + "1" * 64
    write_json(expected / "bundle.json", expected_manifest)

    actual_manifest = json.loads((actual / "bundle.json").read_text())
    actual_manifest["bundle_digest"] = "sha256:" + "2" * 64
    write_json(actual / "bundle.json", actual_manifest)

    report_payload = json.loads((actual / "validation-report.json").read_text())
    report_payload["metadata"]["data_validation_mode"] = (
        "release_manifest_and_artifact_metadata"
    )
    write_json(actual / "validation-report.json", report_payload)

    assert compare_bundle_directories(expected, actual) == []
