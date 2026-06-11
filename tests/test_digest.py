from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import generated_bundle, write_json

from policyengine_bundles.digest import (
    compute_bundle_digest,
    verify_bundle_digest,
    verify_bundle_digests,
    write_bundle_digest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compute_bundle_digest_ignores_run_local_timestamp_fields(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, output_name="bundle")
    digest = compute_bundle_digest(bundle_dir)
    bundle_path = bundle_dir / "bundle.json"
    bundle = json.loads(bundle_path.read_text())
    bundle["created_at"] = "2099-01-01T00:00:00Z"
    write_json(bundle_path, bundle)
    report_path = bundle_dir / "validation-report.json"
    report = json.loads(report_path.read_text())
    report["generated_at"] = "2099-01-01T00:00:00Z"
    write_json(report_path, report)

    assert compute_bundle_digest(bundle_dir) == digest


def test_compute_bundle_digest_changes_when_country_content_changes(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, output_name="bundle")
    digest = compute_bundle_digest(bundle_dir)
    country_path = bundle_dir / "countries" / "us.json"
    country = json.loads(country_path.read_text())
    country["datasets"]["enhanced_cps_2024"]["size_bytes"] = 13
    write_json(country_path, country)

    assert compute_bundle_digest(bundle_dir) != digest


def test_compute_bundle_digest_changes_when_embedded_manifest_changes(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(
        tmp_path,
        embed_local_manifests=True,
        output_name="bundle",
    )
    digest = compute_bundle_digest(bundle_dir)
    embedded_manifest = bundle_dir / "source-manifests/us/release_manifest.json"
    embedded_payload = json.loads(embedded_manifest.read_text())
    embedded_payload["metadata"]["changed_after_generation"] = True
    write_json(embedded_manifest, embedded_payload)

    assert compute_bundle_digest(bundle_dir) != digest


def test_verify_bundle_digest_rejects_manifest_mismatch(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path, output_name="bundle")
    write_bundle_digest(bundle_dir)
    bundle_path = bundle_dir / "bundle.json"
    bundle = json.loads(bundle_path.read_text())
    bundle["bundle_digest"] = "sha256:" + "0" * 64
    write_json(bundle_path, bundle)

    with pytest.raises(ValueError, match="bundle_digest"):
        verify_bundle_digest(bundle_dir)


def test_verify_bundle_digests_requires_committed_digest(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path, output_name="bundle")
    bundles_root = tmp_path / "bundles"
    committed_bundle = bundles_root / "4.4.0"
    bundles_root.mkdir()
    bundle_dir.rename(committed_bundle)

    failures = verify_bundle_digests(bundles_root)

    assert failures == [f"{committed_bundle}: missing bundle_digest"]


def test_verify_bundle_digests_skips_legacy_bundles(tmp_path: Path) -> None:
    bundles_root = tmp_path / "bundles"
    bundles_root.mkdir()
    shutil.copytree(REPO_ROOT / "bundles" / "4.4.2", bundles_root / "4.4.2")

    failures = verify_bundle_digests(bundles_root)

    assert failures == []


def test_verify_bundle_digests_rejects_stale_committed_digest(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path, output_name="bundle")
    bundles_root = tmp_path / "bundles"
    committed_bundle = bundles_root / "4.4.0"
    bundles_root.mkdir()
    bundle_dir.rename(committed_bundle)
    write_bundle_digest(committed_bundle)
    country_path = committed_bundle / "countries" / "us.json"
    country = json.loads(country_path.read_text())
    country["datasets"]["enhanced_cps_2024"]["size_bytes"] = 13
    write_json(country_path, country)

    failures = verify_bundle_digests(bundles_root)

    assert len(failures) == 1
    assert str(committed_bundle) in failures[0]
    assert "bundle_digest does not match" in failures[0]
