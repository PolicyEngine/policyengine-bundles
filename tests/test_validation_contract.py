from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.lockfiles import solve_lockfiles
from policyengine_bundles.validation import load_bundle_directory


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
    return output_dir


def add_install_targets(bundle_dir: Path) -> None:
    def fake_runner(command: list[str]) -> None:
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("# generated\n")

    solve_lockfiles(bundle_dir, runner=fake_runner)


def test_load_bundle_directory_rejects_profile_unknown_package(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["profiles"]["us"]["packages"].append("missing-package")
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="unknown packages"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_country_package_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    country_json = bundle_dir / "countries" / "us.json"
    payload = json.loads(country_json.read_text())
    payload["core_package"]["version"] = "3.27.0"
    write_json(country_json, payload)

    with pytest.raises(ValueError, match="does not match bundle.json packages entry"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_report_version_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    report_json = bundle_dir / "validation-report.json"
    payload = json.loads(report_json.read_text())
    payload["bundle_version"] = "4.4.1"
    write_json(report_json, payload)

    with pytest.raises(ValueError, match="Validation report bundle_version"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_policyengine_version_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["policyengine"]["version"] = "4.4.1"
    payload["packages"]["policyengine"]["version"] = "4.4.1"
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="does not match bundle_version"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_policyengine_package_pin_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["packages"]["policyengine"]["sha256"] = "d" * 64
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="policyengine pin must match"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_install_target_key_version_drift(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    add_install_targets(bundle_dir)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    install_targets = payload["profiles"]["us"]["install_targets"]
    install_targets["py314"] = install_targets.pop("py313")
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="install target key"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_invalid_install_target_python_version(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    add_install_targets(bundle_dir)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["profiles"]["us"]["install_targets"]["py313"]["python_version"] = "3"
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="Python version must use"):
        load_bundle_directory(bundle_dir)


def test_load_bundle_directory_rejects_legacy_profile_install_artifacts(
    tmp_path: Path,
) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["profiles"]["us"]["constraints"] = {
        "py313": "constraints/constraints-us-py313.txt"
    }
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        load_bundle_directory(bundle_dir)
