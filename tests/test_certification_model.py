from __future__ import annotations

import pytest

from policyengine_bundles.models import DataArtifact, PackagePin


def test_hash_pinned_artifact_requires_sha256() -> None:
    with pytest.raises(ValueError, match="require sha256"):
        DataArtifact.model_validate(
            {
                "kind": "microdata",
                "path": "long_term/2050.h5",
                "repo_id": "policyengine/policyengine-us-data",
                "revision": "crfb-longrun-20260517",
                "status": "hash_pinned",
            }
        )


def test_unverified_artifact_requires_missing_reason() -> None:
    with pytest.raises(ValueError, match="missing_reason"):
        DataArtifact.model_validate(
            {
                "kind": "microdata",
                "path": "long_term/2050.h5",
                "repo_id": "policyengine/policyengine-us-data",
                "revision": "crfb-longrun-20260517",
                "status": "unverified",
            }
        )


def test_partially_certified_artifact_requires_certification() -> None:
    with pytest.raises(ValueError, match="require certification"):
        DataArtifact.model_validate(
            {
                "kind": "microdata",
                "path": "long_term/2050.h5",
                "repo_id": "policyengine/policyengine-us-data",
                "revision": "crfb-longrun-20260517",
                "status": "partially_certified",
                "sha256": "a" * 64,
            }
        )


def test_partially_certified_artifact_requires_scopes_and_limitations() -> None:
    with pytest.raises(ValueError, match="require scopes"):
        DataArtifact.model_validate(
            {
                "kind": "microdata",
                "path": "long_term/2050.h5",
                "repo_id": "policyengine/policyengine-us-data",
                "revision": "crfb-longrun-20260517",
                "status": "partially_certified",
                "sha256": "a" * 64,
                "certification": {
                    "certified_by": "policyengine-bundles tests",
                    "limitations": ["not fully validated for every year"],
                },
            }
        )

    with pytest.raises(ValueError, match="require limitations"):
        DataArtifact.model_validate(
            {
                "kind": "microdata",
                "path": "long_term/2050.h5",
                "repo_id": "policyengine/policyengine-us-data",
                "revision": "crfb-longrun-20260517",
                "status": "partially_certified",
                "sha256": "a" * 64,
                "certification": {
                    "certified_by": "policyengine-bundles tests",
                    "scopes": ["h5 hash verified"],
                },
            }
        )


def test_partially_certified_artifact_accepts_evidence() -> None:
    artifact = DataArtifact.model_validate(
        {
            "kind": "microdata",
            "path": "long_term/2050.h5",
            "repo_id": "policyengine/policyengine-us-data",
            "revision": "crfb-longrun-20260517",
            "status": "partially_certified",
            "sha256": "a" * 64,
            "metadata_sha256": "b" * 64,
            "certification": {
                "certified_by": "policyengine-bundles tests",
                "scopes": ["h5 hash verified"],
                "limitations": ["not fully validated for every year"],
                "evidence": [
                    {
                        "kind": "validation_check",
                        "subject": "long_term_cps_2050",
                        "subject_sha256": "a" * 64,
                    }
                ],
            },
        }
    )

    assert artifact.status == "partially_certified"
    assert artifact.certification is not None
    assert artifact.certification.evidence[0].kind == "validation_check"


def test_package_pin_can_mark_bundle_carrier() -> None:
    package = PackagePin.model_validate(
        {
            "name": "policyengine",
            "version": "4.10.0",
            "role": "bundle_carrier",
        }
    )

    assert package.is_bundle_carrier
