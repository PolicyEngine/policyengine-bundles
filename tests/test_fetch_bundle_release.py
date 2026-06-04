from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.lockfiles import solve_lockfiles
from policyengine_bundles.release import (
    package_bundle_release,
    verify_and_unpack_bundle_release,
    verify_bundle_release_assets,
)


def certified_bundle(tmp_path: Path) -> Path:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "4.4.0"
    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        testing_only=True,
    )

    def fake_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("policyengine-core==3.26.0\n")

    solve_lockfiles(output_dir, runner=fake_runner)
    report_path = output_dir / "validation-report.json"
    report = json.loads(report_path.read_text())
    report["status"] = "passed"
    report["metadata"] = {
        "validation_scope": "full",
        "verify_data": True,
        "validate_runtime": True,
    }
    for check in report["checks"]:
        check["status"] = "passed"
    write_json(report_path, report)
    return output_dir


def test_verify_and_unpack_bundle_release_checks_digest(tmp_path: Path) -> None:
    bundle_dir = certified_bundle(tmp_path)
    package_bundle_release(bundle_dir, tmp_path / "dist")

    unpacked = verify_and_unpack_bundle_release(
        version="4.4.0",
        dist_dir=tmp_path / "dist",
        output_dir=tmp_path / "unpacked",
    )

    assert (unpacked / "bundle.json").exists()
    assert unpacked.name == "policyengine-bundle-4.4.0"


def test_verify_bundle_release_assets_rejects_missing_asset(tmp_path: Path) -> None:
    bundle_dir = certified_bundle(tmp_path)
    package_bundle_release(bundle_dir, tmp_path / "dist")
    (tmp_path / "dist" / "policyengine-bundle-4.4.0.tar.gz.sha256").unlink()

    with pytest.raises(ValueError, match="Missing bundle release assets"):
        verify_bundle_release_assets(version="4.4.0", dist_dir=tmp_path / "dist")


def test_verify_bundle_release_assets_rejects_wrong_checksum(tmp_path: Path) -> None:
    bundle_dir = certified_bundle(tmp_path)
    package_bundle_release(bundle_dir, tmp_path / "dist")
    checksum_path = tmp_path / "dist" / "policyengine-bundle-4.4.0.tar.gz.sha256"
    checksum_path.write_text("0" * 64 + "  policyengine-bundle-4.4.0.tar.gz\n")

    with pytest.raises(ValueError, match="does not match checksum file"):
        verify_bundle_release_assets(version="4.4.0", dist_dir=tmp_path / "dist")


def test_verify_and_unpack_bundle_release_rejects_summary_digest_mismatch(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path)
    package_bundle_release(bundle_dir, tmp_path / "dist")
    summary_path = tmp_path / "dist" / "policyengine-bundle-4.4.0.json"
    summary = json.loads(summary_path.read_text())
    summary["bundle_digest"] = "sha256:" + "0" * 64
    write_json(summary_path, summary)

    with pytest.raises(ValueError, match="bundle_digest"):
        verify_and_unpack_bundle_release(
            version="4.4.0",
            dist_dir=tmp_path / "dist",
            output_dir=tmp_path / "unpacked",
        )
