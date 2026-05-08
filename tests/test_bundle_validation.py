from __future__ import annotations

import json
from pathlib import Path

from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.bundle_validation import (
    ArtifactVerification,
    validate_bundle,
    verify_artifact_uri,
)
from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.lockfiles import solve_lockfiles


def generated_bundle_with_install_artifacts(tmp_path: Path) -> Path:
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

    def fake_lock_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("# generated\n")

    solve_lockfiles(output_dir, runner=fake_lock_runner)
    return output_dir


def fake_artifact_verifier(uri: str) -> ArtifactVerification:
    if uri.startswith("file://"):
        return verify_artifact_uri(uri)
    return ArtifactVerification(sha256="c" * 64, size_bytes=12)


def test_validate_bundle_runs_profile_checks(tmp_path: Path) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)
    commands: list[list[str]] = []

    def fake_runner(command: list[str]) -> None:
        commands.append(command)

    report = validate_bundle(
        bundle_dir,
        runner=fake_runner,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "passed"
    check_names = {check.name for check in report.checks}
    assert "data_release_manifest_contract" in check_names
    assert "verify_direct_package_versions" in check_names
    assert "us_household_smoke" in check_names
    assert any(command[0] == "uv" and command[1] == "venv" for command in commands)
    assert all(
        "validated_on_platform" in check.details
        for check in report.checks
        if check.name in {"constraints_present", "lockfile_present", "create_venv"}
    )


def test_validate_bundle_reports_runtime_failure(tmp_path: Path) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)

    def failing_runner(command: list[str]) -> None:
        if command[0] != "uv":
            raise RuntimeError("boom")

    report = validate_bundle(
        bundle_dir,
        runner=failing_runner,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "verify_direct_package_versions" and check.status == "failed"
        for check in report.checks
    )


def test_validate_bundle_fails_without_constraints(tmp_path: Path) -> None:
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

    report = validate_bundle(
        output_dir,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "install_targets_complete" and check.status == "failed"
        for check in report.checks
    )


def test_validate_bundle_fails_when_install_target_missing_for_declared_python(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["metadata"]["python_versions"] = ["3.13", "3.14"]
    write_json(bundle_json, payload)

    report = validate_bundle(
        bundle_dir,
        runner=lambda command: None,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "install_targets_complete"
        and check.status == "failed"
        and any(
            "missing install targets" in failure
            for failure in check.details["failures"]
        )
        for check in report.checks
    )


def test_validate_bundle_fails_when_install_target_not_declared(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["profiles"]["us"]["install_targets"]["py314"] = {
        "python_version": "3.14",
        "constraints": "install/us/py313/constraints.txt",
        "lockfile": "install/us/py313/pylock.toml",
        "resolver": "uv",
    }
    write_json(bundle_json, payload)

    report = validate_bundle(
        bundle_dir,
        runner=lambda command: None,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "install_targets_complete"
        and check.status == "failed"
        and any("not declared" in failure for failure in check.details["failures"])
        for check in report.checks
    )


def test_validate_bundle_uses_embedded_release_manifest(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "bundle"
    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        embed_local_manifests=True,
    )
    release_path.unlink()

    def fake_lock_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("# generated\n")

    solve_lockfiles(output_dir, runner=fake_lock_runner)
    report = validate_bundle(
        output_dir,
        runner=lambda command: None,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "passed"
    assert any(
        check.name == "data_release_manifest_contract" and check.status == "passed"
        for check in report.checks
    )


def test_validate_bundle_rejects_missing_embedded_release_manifest(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "bundle"
    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        embed_local_manifests=True,
    )
    embedded_manifest = output_dir / "source-manifests" / "us" / "release_manifest.json"
    embedded_manifest.unlink()

    def fake_lock_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("# generated\n")

    solve_lockfiles(output_dir, runner=fake_lock_runner)
    report = validate_bundle(
        output_dir,
        runner=lambda command: None,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "data_release_manifest_contract"
        and check.status == "failed"
        and any(
            "embedded release manifest missing" in failure
            for failure in check.details["failures"]
        )
        for check in report.checks
    )


def test_validate_bundle_fails_when_artifact_hash_mismatches(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)

    def bad_artifact_verifier(uri: str) -> ArtifactVerification:
        if uri.startswith("file://"):
            return verify_artifact_uri(uri)
        return ArtifactVerification(sha256="d" * 64, size_bytes=12)

    report = validate_bundle(
        bundle_dir,
        runner=lambda command: None,
        artifact_verifier=bad_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "data_release_manifest_contract" and check.status == "failed"
        for check in report.checks
    )


def test_validate_bundle_fails_when_lockfile_missing(tmp_path: Path) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)
    (bundle_dir / "install" / "us" / "py313" / "pylock.toml").unlink()

    report = validate_bundle(
        bundle_dir,
        runner=lambda command: None,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "lockfile_present" and check.status == "failed"
        for check in report.checks
    )


def test_validate_bundle_fails_when_lockfile_is_not_toml(tmp_path: Path) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)
    (bundle_dir / "install" / "us" / "py313" / "pylock.toml").write_text("not = [toml")

    report = validate_bundle(
        bundle_dir,
        runner=lambda command: None,
        artifact_verifier=fake_artifact_verifier,
    )

    assert report.status == "failed"
    assert any(
        check.name == "lockfile_present" and check.status == "failed"
        for check in report.checks
    )
