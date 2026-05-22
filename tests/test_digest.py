from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.digest import (
    compute_bundle_digest,
    verify_bundle_digest,
    verify_bundle_digests,
    write_bundle_digest,
)
from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.lockfiles import solve_lockfiles


def generated_bundle(tmp_path: Path) -> Path:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "bundle"
    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        testing_only=True,
    )

    def fake_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("# generated from /tmp/run\npolicyengine==4.4.0\n")

    solve_lockfiles(output_dir, runner=fake_runner)
    return output_dir


def test_compute_bundle_digest_ignores_run_local_report_fields(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    digest = compute_bundle_digest(bundle_dir)
    report_path = bundle_dir / "validation-report.json"
    report = json.loads(report_path.read_text())
    report["generated_at"] = "2099-01-01T00:00:00Z"
    report["checks"][0]["details"]["validated_on_platform"] = "macos"
    write_json(report_path, report)

    assert compute_bundle_digest(bundle_dir) == digest


def test_compute_bundle_digest_changes_when_lock_content_changes(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    digest = compute_bundle_digest(bundle_dir)
    lockfile = bundle_dir / "install/us/py313/pylock.toml"
    lockfile.write_text(lockfile.read_text() + 'created-by = "different"\n')

    assert compute_bundle_digest(bundle_dir) != digest


def test_compute_bundle_digest_changes_when_embedded_manifest_changes(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    bundle_dir = tmp_path / "bundle"
    generate_bundle(
        candidate_path,
        bundle_dir,
        package_resolver=fake_resolver,
        embed_local_manifests=True,
    )
    digest = compute_bundle_digest(bundle_dir)
    embedded_manifest = bundle_dir / "source-manifests/us/release_manifest.json"
    embedded_payload = json.loads(embedded_manifest.read_text())
    embedded_payload["metadata"]["changed_after_generation"] = True
    write_json(embedded_manifest, embedded_payload)

    assert compute_bundle_digest(bundle_dir) != digest


def test_verify_bundle_digest_rejects_manifest_mismatch(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path)
    write_bundle_digest(bundle_dir)
    bundle_path = bundle_dir / "bundle.json"
    bundle = json.loads(bundle_path.read_text())
    bundle["bundle_digest"] = "sha256:" + "0" * 64
    write_json(bundle_path, bundle)

    with pytest.raises(ValueError, match="bundle_digest"):
        verify_bundle_digest(bundle_dir)


def test_verify_bundle_digests_requires_committed_digest(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundles_root = tmp_path / "bundles"
    committed_bundle = bundles_root / "4.4.0"
    bundles_root.mkdir()
    bundle_dir.rename(committed_bundle)

    failures = verify_bundle_digests(bundles_root)

    assert failures == [f"{committed_bundle}: missing bundle_digest"]


def test_verify_bundle_digests_rejects_stale_committed_digest(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundles_root = tmp_path / "bundles"
    committed_bundle = bundles_root / "4.4.0"
    bundles_root.mkdir()
    bundle_dir.rename(committed_bundle)
    write_bundle_digest(committed_bundle)
    constraints = committed_bundle / "install/us/py313/constraints.txt"
    constraints.write_text(constraints.read_text() + "policyengine-core==3.26.0\n")

    failures = verify_bundle_digests(bundles_root)

    assert len(failures) == 1
    assert str(committed_bundle) in failures[0]
    assert "bundle_digest does not match" in failures[0]
