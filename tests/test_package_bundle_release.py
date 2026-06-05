from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from conftest import generated_bundle, write_json

from policyengine_bundles.normalization import bundle_files
from policyengine_bundles.release import package_bundle_release


def certified_bundle(
    tmp_path: Path,
    *,
    embed_local_manifests: bool = False,
) -> Path:
    return generated_bundle(
        tmp_path,
        embed_local_manifests=embed_local_manifests,
        output_name="4.4.0",
    )


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


def test_package_bundle_release_rejects_non_registry_validation_report(
    tmp_path: Path,
) -> None:
    bundle_dir = certified_bundle(tmp_path)
    report_path = bundle_dir / "validation-report.json"
    report = json.loads(report_path.read_text())
    report["metadata"]["validation_kind"] = "runtime"
    write_json(report_path, report)

    with pytest.raises(ValueError, match="registry validation"):
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
    country_path = bundle_dir / "countries" / "us.json"
    country = json.loads(country_path.read_text())
    country["datasets"]["enhanced_cps_2024"]["size_bytes"] = 13
    write_json(country_path, country)

    with pytest.raises(ValueError, match="bundle_digest"):
        package_bundle_release(bundle_dir, tmp_path / "dist-again")
