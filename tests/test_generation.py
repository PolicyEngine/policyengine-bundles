from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import fake_resolver, release_manifest, write_candidate, write_json

from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.validation import load_bundle_directory


def test_generate_bundle_from_candidate(tmp_path: Path) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    release_payload = release_manifest()
    write_json(release_path, release_payload)
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    output_dir = tmp_path / "bundle"

    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        testing_only=True,
    )

    bundle = load_bundle_directory(output_dir)
    country = bundle.countries["us"]
    assert bundle.manifest.schema_version == 2
    assert bundle.manifest.bundle_version == "4.4.0"
    assert bundle.manifest.policyengine.role == "bundle_carrier"
    assert bundle.manifest.policyengine.version == "4.4.0"
    assert country.schema_version == 2
    assert country.default_dataset == "enhanced_cps_2024"
    assert country.compatibility.basis == "bundle_candidate"
    assert country.compatibility.model_package == country.model_package
    assert country.compatibility.core_package == country.core_package
    assert country.compatibility.release_manifest_uri == release_path.as_uri()
    assert country.artifact_release.release_manifest_sha256 == (
        country.compatibility.release_manifest_sha256
    )


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


def test_generate_bundle_supports_multiple_countries(tmp_path: Path) -> None:
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
            "schema_version": 2,
            "bundle_version": "4.4.0",
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
    assert sorted(bundle.manifest.countries) == ["uk", "us"]
    assert bundle.countries["uk"].model_package.name == "policyengine-uk"
    assert bundle.countries["us"].model_package.name == "policyengine-us"


def test_generate_bundle_rejects_unsupported_manifest_uri(tmp_path: Path) -> None:
    candidate_path = write_candidate(tmp_path, "s3://example/release_manifest.json")

    with pytest.raises(ValueError, match="Unsupported release manifest URI"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_specifier_package_version(tmp_path: Path) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    payload = json.loads(candidate_path.read_text())
    payload["packages"]["policyengine-us"] = ">=1.0.0"
    write_json(candidate_path, payload)

    with pytest.raises(ValueError, match="exact version"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_unknown_country_model_package(
    tmp_path: Path,
) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())
    payload = json.loads(candidate_path.read_text())
    payload["countries"]["us"]["model_package"] = "policyengine-uk"
    write_json(candidate_path, payload)

    with pytest.raises(ValueError, match="unknown model package"):
        generate_bundle(
            candidate_path,
            tmp_path / "bundle",
            package_resolver=fake_resolver,
            testing_only=True,
        )


def test_generate_bundle_rejects_local_manifest_without_test_mode(
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


def test_generate_bundle_can_embed_local_release_manifest(tmp_path: Path) -> None:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, release_manifest())
    candidate_path = write_candidate(tmp_path, release_path.as_uri())

    generate_bundle(
        candidate_path,
        tmp_path / "bundle",
        package_resolver=fake_resolver,
        embed_local_manifests=True,
    )

    bundle = load_bundle_directory(tmp_path / "bundle")
    assert (
        bundle.countries["us"].data_package.release_manifest_path
        == "source-manifests/us/release_manifest.json"
    )
    assert (tmp_path / "bundle" / "source-manifests/us/release_manifest.json").exists()
