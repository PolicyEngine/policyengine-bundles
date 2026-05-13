from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.lockfiles import solve_lockfiles
from policyengine_bundles.normalization import bundle_files
from policyengine_bundles.release import package_bundle_release


def certified_bundle(
    tmp_path: Path,
    *,
    embed_local_manifests: bool = False,
) -> Path:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "4.4.0"
    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        testing_only=True,
        embed_local_manifests=embed_local_manifests,
    )

    def fake_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("policyengine==4.4.0\n")

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


def test_package_bundle_release_writes_archive_checksum_and_digest(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path)
    archive_path, checksum_path = package_bundle_release(
        bundle_dir,
        tmp_path / "dist",
    )

    assert archive_path.exists()
    assert checksum_path.exists()
    bundle = json.loads((bundle_dir / "bundle.json").read_text())
    assert bundle["bundle_digest"].startswith("sha256:")
    with tarfile.open(archive_path) as archive:
        assert "policyengine-bundle-4.4.0/bundle.json" in archive.getnames()


def test_package_bundle_release_archive_matches_digest_file_set(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path, embed_local_manifests=True)
    archive_path, _checksum_path = package_bundle_release(
        bundle_dir,
        tmp_path / "dist",
    )
    expected_names = {
        f"policyengine-bundle-4.4.0/{path.as_posix()}"
        for path in bundle_files(bundle_dir)
    }

    with tarfile.open(archive_path) as archive:
        assert set(archive.getnames()) == expected_names


def test_package_bundle_release_rejects_failed_validation_report(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path)
    report_path = bundle_dir / "validation-report.json"
    report = json.loads(report_path.read_text())
    report["status"] = "failed"
    write_json(report_path, report)

    with pytest.raises(ValueError, match="passing validation report"):
        package_bundle_release(bundle_dir, tmp_path / "dist")


def test_package_bundle_release_rejects_partial_validation_report(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path)
    report_path = bundle_dir / "validation-report.json"
    report = json.loads(report_path.read_text())
    report["metadata"]["validation_scope"] = "partial"
    write_json(report_path, report)

    with pytest.raises(ValueError, match="validation_scope='full'"):
        package_bundle_release(bundle_dir, tmp_path / "dist")


def test_package_bundle_release_rejects_skipped_validation_checks(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path)
    report_path = bundle_dir / "validation-report.json"
    report = json.loads(report_path.read_text())
    report["checks"][0]["status"] = "skipped"
    write_json(report_path, report)

    with pytest.raises(ValueError, match="no skipped validation checks"):
        package_bundle_release(bundle_dir, tmp_path / "dist")


def test_package_bundle_release_rejects_stale_recorded_digest(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path)
    package_bundle_release(bundle_dir, tmp_path / "dist")
    constraints = bundle_dir / "install/us/py313/constraints.txt"
    constraints.write_text(constraints.read_text() + "policyengine-core==3.26.0\n")

    with pytest.raises(ValueError, match="bundle_digest"):
        package_bundle_release(bundle_dir, tmp_path / "dist-again")
