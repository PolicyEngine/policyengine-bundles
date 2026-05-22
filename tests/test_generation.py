from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.generation import LoadedManifest, generate_bundle
from policyengine_bundles.validation import load_bundle_directory


def test_generate_bundle_from_candidate(tmp_path: Path) -> None:
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

    bundle = load_bundle_directory(output_dir)
    assert bundle.manifest.bundle_version == "4.4.0"
    assert bundle.manifest.policyengine.role == "bundle_carrier"
    assert bundle.manifest.policyengine.sha256 is None
    assert bundle.manifest.packages["policyengine"] == bundle.manifest.policyengine
    assert bundle.manifest.profiles["us"].packages == [
        "policyengine",
        "policyengine-core",
        "policyengine-us",
    ]
    assert bundle.countries["us"].core_package.version == "3.26.0"
    assert bundle.countries["us"].default_dataset == "enhanced_cps_2024"


def test_generate_bundle_accepts_legacy_release_manifest_created_at(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    payload = release_manifest()
    payload["created_at"] = "2026-04-15T19:03:37.831756Z"
    write_json(release_path, payload)
    candidate_path = write_candidate(tmp_path, release_path.as_uri())

    generate_bundle(
        candidate_path,
        tmp_path / "bundle",
        package_resolver=fake_resolver,
        testing_only=True,
    )


def test_generate_bundle_supports_all_profile(tmp_path: Path) -> None:
    us_release_path = tmp_path / "us-release-manifest.json"
    uk_release_path = tmp_path / "uk-release-manifest.json"
    write_json(us_release_path, release_manifest())
    write_json(
        uk_release_path,
        release_manifest(
            data_package_name="policyengine-uk-data",
            model_package_name="policyengine-uk",
            artifact_key="enhanced_frs_2023_24",
            repo_id="policyengine/policyengine-uk-data-private",
        ),
    )
    candidate_path = tmp_path / "candidate.json"
    write_json(
        candidate_path,
        {
            "schema_version": 1,
            "bundle_version": "4.4.0",
            "policyengine_version": "4.4.0",
            "python_versions": ["3.13"],
            "profiles": ["us", "uk", "all"],
            "packages": {
                "policyengine-core": "3.26.0",
                "policyengine-us": "1.0.0",
                "policyengine-uk": "1.0.0",
            },
            "countries": {
                "us": {
                    "model_package": "policyengine-us",
                    "data_release_manifest_uri": us_release_path.as_uri(),
                },
                "uk": {
                    "model_package": "policyengine-uk",
                    "data_release_manifest_uri": uk_release_path.as_uri(),
                },
            },
        },
    )
    output_dir = tmp_path / "bundle"

    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        testing_only=True,
    )

    bundle = load_bundle_directory(output_dir)
    assert bundle.manifest.profiles["all"].packages == [
        "policyengine",
        "policyengine-core",
        "policyengine-uk",
        "policyengine-us",
    ]
    assert bundle.manifest.profiles["all"].countries == ["uk", "us"]


def test_generate_bundle_rejects_unsupported_manifest_uri(tmp_path: Path) -> None:
    candidate_path = write_candidate(tmp_path, "s3://example/release_manifest.json")

    with pytest.raises(ValueError, match="Unsupported release manifest URI"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_policyengine_version_drift(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    payload = {
        "schema_version": 1,
        "bundle_version": "4.4.0",
        "policyengine_version": "4.4.1",
        "python_versions": ["3.13"],
        "profiles": ["us"],
        "packages": {
            "policyengine-core": "3.26.0",
            "policyengine-us": "1.0.0",
        },
        "countries": {
            "us": {
                "model_package": "policyengine-us",
                "data_release_manifest_uri": release_path.as_uri(),
            }
        },
    }
    write_json(candidate_path, payload)

    with pytest.raises(ValueError, match="policyengine_version must match"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_missing_python_versions(tmp_path: Path) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    payload = json.loads(candidate_path.read_text())
    payload["python_versions"] = []
    write_json(candidate_path, payload)

    with pytest.raises(ValueError, match="at least 1 item"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_invalid_python_version(tmp_path: Path) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    payload = json.loads(candidate_path.read_text())
    payload["python_versions"] = ["3"]
    write_json(candidate_path, payload)

    with pytest.raises(ValueError, match="Python version must use"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_core_mismatch(tmp_path: Path) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest(core_version="3.25.0"))
    candidate_path = write_candidate(tmp_path, release_path.as_uri())

    with pytest.raises(ValueError, match="policyengine-core==3.26.0"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_certified_artifact_without_sha(tmp_path: Path) -> None:
    payload = copy.deepcopy(release_manifest())
    payload["artifacts"]["enhanced_cps_2024"].pop("sha256")
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, payload)
    candidate_path = write_candidate(tmp_path, release_path.as_uri())

    with pytest.raises(ValueError, match="Certified data artifacts require sha256"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_missing_build_metadata(tmp_path: Path) -> None:
    payload = copy.deepcopy(release_manifest())
    payload.pop("build")
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, payload)
    candidate_path = write_candidate(tmp_path, release_path.as_uri())

    with pytest.raises(ValueError, match="must record build metadata"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_missing_core_build_metadata(tmp_path: Path) -> None:
    payload = copy.deepcopy(release_manifest())
    payload["build"].pop("built_with_core_package")
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, payload)
    candidate_path = write_candidate(tmp_path, release_path.as_uri())

    with pytest.raises(ValueError, match="built_with_core_package"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_local_manifest_for_certified_bundle(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())

    with pytest.raises(ValueError, match="Local file release manifests"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
        )


def test_generate_bundle_embeds_local_manifest_when_requested(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    payload = release_manifest()
    write_json(release_path, payload)
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "bundle"

    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        embed_local_manifests=True,
    )

    embedded_path = output_dir / "source-manifests" / "us" / "release_manifest.json"
    bundle = load_bundle_directory(output_dir)
    assert embedded_path.exists()
    assert json.loads(embedded_path.read_text()) == json.loads(release_path.read_text())
    assert (
        bundle.countries["us"].data_package.release_manifest_path
        == "source-manifests/us/release_manifest.json"
    )
    assert bundle.countries["us"].artifact_release.release_manifest_uri is None
    assert (
        bundle.countries["us"].metadata["input_release_manifest_uri"]
        == release_path.as_uri()
    )


def test_generate_bundle_rewrites_artifacts_to_loaded_hf_revision(
    tmp_path: Path,
) -> None:
    payload = release_manifest(data_package_version="1.113.1")
    content = json.dumps(payload, sort_keys=True).encode()
    candidate_path = write_candidate(
        tmp_path,
        "hf://model/policyengine/policyengine-us-data@abc123/releases/1.113.1/release_manifest.json",
    )
    output_dir = tmp_path / "bundle"

    def manifest_loader(uri: str) -> LoadedManifest:
        return LoadedManifest(
            payload=payload,
            uri=uri,
            sha256="d" * 64,
            content=content,
            repo_id="policyengine/policyengine-us-data",
            repo_type="model",
            revision="abc123",
            path="releases/1.113.1/release_manifest.json",
        )

    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        manifest_loader=manifest_loader,
    )

    country = load_bundle_directory(output_dir).countries["us"]
    artifact = country.datasets["enhanced_cps_2024"]
    assert country.data_package.version == "1.113.1"
    assert country.artifact_release.version == "abc123"
    assert artifact.revision == "abc123"
    assert artifact.uri is not None
    assert "@abc123/" in artifact.uri
