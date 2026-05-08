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
    generate_bundle(candidate_path, output_dir, package_resolver=fake_resolver)
    return output_dir


def test_solve_lockfiles_records_generated_install_artifacts(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path)
    commands: list[list[str]] = []

    def fake_runner(command: list[str]) -> None:
        commands.append(command)
        output_path = Path(command[command.index("--output-file") + 1])
        output_path.write_text("# generated\n")

    solve_lockfiles(bundle_dir, runner=fake_runner)

    bundle = load_bundle_directory(bundle_dir)
    assert bundle.manifest.profiles["us"].constraints == {
        "py313": "constraints/constraints-us-py313.txt"
    }
    assert bundle.manifest.profiles["us"].lockfiles == {
        "py313": "lockfiles/pylock.us.py313.toml"
    }
    assert len(commands) == 2
    assert commands[0][0:3] == ["uv", "pip", "compile"]
    assert "--generate-hashes" in commands[0]
    assert commands[0][commands[0].index("--python-platform") + 1] == "linux"
    assert commands[1][commands[1].index("--python-platform") + 1] == "linux"
    assert commands[1][commands[1].index("--format") + 1] == "pylock.toml"
    assert bundle.manifest.metadata["python_platform"] == "linux"


def test_solve_lockfiles_rejects_unknown_profile_package(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["profiles"]["us"]["packages"].append("missing-package")
    write_json(bundle_json, payload)

    with pytest.raises(ValueError, match="unknown package"):
        solve_lockfiles(bundle_dir, runner=lambda command: None)


def test_solve_lockfiles_rejects_specifier_only_package(tmp_path: Path) -> None:
    bundle_dir = generated_bundle(tmp_path)
    bundle_json = bundle_dir / "bundle.json"
    payload = json.loads(bundle_json.read_text())
    payload["packages"]["policyengine-core"].pop("version")
    payload["packages"]["policyengine-core"]["specifier"] = ">=3.26.0"
    payload["packages"]["policyengine-core"]["resolution_status"] = "specifier_only"
    write_json(bundle_json, payload)
    country_json = bundle_dir / "countries" / "us.json"
    country_payload = json.loads(country_json.read_text())
    country_payload["core_package"].pop("version")
    country_payload["core_package"]["specifier"] = ">=3.26.0"
    country_payload["core_package"]["resolution_status"] = "specifier_only"
    write_json(country_json, country_payload)

    with pytest.raises(ValueError, match="exact-pinned"):
        solve_lockfiles(bundle_dir, runner=lambda command: None)
