from __future__ import annotations

from pathlib import Path

import pytest
from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.bundle_validation import validate_bundle
from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.lockfiles import solve_lockfiles


def generated_bundle_with_install_artifacts(tmp_path: Path) -> Path:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "bundle"
    generate_bundle(candidate_path, output_dir, package_resolver=fake_resolver)

    def fake_lock_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("# generated\n")

    solve_lockfiles(output_dir, runner=fake_lock_runner)
    return output_dir


def test_validate_bundle_runs_profile_checks(tmp_path: Path) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)
    commands: list[list[str]] = []

    def fake_runner(command: list[str]) -> None:
        commands.append(command)

    report = validate_bundle(bundle_dir, runner=fake_runner)

    assert report.status == "passed"
    check_names = {check.name for check in report.checks}
    assert "data_release_manifest_contract" in check_names
    assert "verify_direct_package_versions" in check_names
    assert "us_household_smoke" in check_names
    assert any(command[0] == "uv" and command[1] == "venv" for command in commands)


def test_validate_bundle_reports_runtime_failure(tmp_path: Path) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)

    def failing_runner(command: list[str]) -> None:
        if command[0] != "uv":
            raise RuntimeError("boom")

    report = validate_bundle(bundle_dir, runner=failing_runner)

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
    generate_bundle(candidate_path, output_dir, package_resolver=fake_resolver)

    report = validate_bundle(output_dir)

    assert report.status == "failed"
    assert any(
        check.name == "install_artifacts_present" and check.status == "failed"
        for check in report.checks
    )


def test_validate_bundle_rejects_unknown_profile(tmp_path: Path) -> None:
    bundle_dir = generated_bundle_with_install_artifacts(tmp_path)

    with pytest.raises(ValueError, match="Unknown bundle profiles"):
        validate_bundle(bundle_dir, profiles=["missing"])
