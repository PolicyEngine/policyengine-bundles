from __future__ import annotations

import json
from pathlib import Path

from policyengine_bundles.bundle_validation import validate_bundle
from policyengine_bundles.generation import generate_bundle
from policyengine_bundles.models import PackagePin

HASH = "a" * 64


def fake_resolver(name: str, version: str) -> PackagePin:
    return PackagePin(
        name=name,
        version=version,
        resolution_status="pinned",
        wheel_url=f"https://example.test/{name}-{version}.whl",
        sdist_url=f"https://example.test/{name}-{version}.tar.gz",
        sha256=HASH,
        source="test",
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True))


def release_manifest(
    *,
    data_package_name: str = "policyengine-us-data",
    data_package_version: str = "1.0.0",
    model_package_name: str = "policyengine-us",
    model_package_version: str = "1.0.0",
    core_version: str = "3.26.0",
    artifact_key: str = "enhanced_cps_2024",
    repo_id: str = "policyengine/policyengine-us-data",
) -> dict:
    return {
        "schema_version": 1,
        "data_package": {
            "name": data_package_name,
            "version": data_package_version,
        },
        "compatible_model_packages": [
            {"name": model_package_name, "specifier": f"=={model_package_version}"}
        ],
        "compatible_core_packages": [
            {"name": "policyengine-core", "specifier": f"=={core_version}"}
        ],
        "default_datasets": {"national": artifact_key},
        "build": {
            "build_id": f"{data_package_name}-{data_package_version}",
            "built_at": "2026-05-08T00:00:00Z",
            "built_with_model_package": {
                "name": model_package_name,
                "version": model_package_version,
                "data_build_fingerprint": "sha256:" + "b" * 64,
                "core": {
                    "name": "policyengine-core",
                    "version": core_version,
                    "resolution_status": "pinned",
                },
            },
            "built_with_core_package": {
                "name": "policyengine-core",
                "version": core_version,
            },
        },
        "artifacts": {
            artifact_key: {
                "kind": "microdata",
                "uri": f"hf://model/{repo_id}@{data_package_version}/{artifact_key}.h5",
                "path": f"{artifact_key}.h5",
                "repo_id": repo_id,
                "revision": data_package_version,
                "sha256": "c" * 64,
                "size_bytes": 12,
                "metadata": {"repo_type": "model"},
            }
        },
        "metadata": {
            "artifact_release": {
                "repo_id": repo_id,
                "repo_type": "model",
                "version": data_package_version,
            }
        },
    }


def write_candidate(
    tmp_path: Path,
    manifest_uri: str,
    *,
    bundle_version: str = "4.4.0",
) -> Path:
    candidate = {
        "schema_version": 2,
        "bundle_version": bundle_version,
        "packages": {
            "policyengine-core": "3.26.0",
            "policyengine-us": "1.0.0",
        },
        "countries": {
            "us": {
                "model_package": "policyengine-us",
                "data_release_manifest_uri": manifest_uri,
            }
        },
    }
    path = tmp_path / "candidate.json"
    write_json(path, candidate)
    return path


def generated_bundle(
    tmp_path: Path,
    *,
    bundle_version: str = "4.4.0",
    validate: bool = True,
    embed_local_manifests: bool = False,
    manifest_payload: dict | None = None,
    output_name: str | None = None,
) -> Path:
    release_path = tmp_path / "us-release-manifest.json"
    write_json(release_path, manifest_payload or release_manifest())
    candidate_path = write_candidate(
        tmp_path,
        release_path.as_uri(),
        bundle_version=bundle_version,
    )
    output_dir = tmp_path / (output_name or bundle_version)
    generate_bundle(
        candidate_path,
        output_dir,
        package_resolver=fake_resolver,
        testing_only=not embed_local_manifests,
        embed_local_manifests=embed_local_manifests,
    )
    if validate:
        validate_bundle(output_dir)
    return output_dir
