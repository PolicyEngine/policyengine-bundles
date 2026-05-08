from __future__ import annotations

import pytest

from policyengine_bundles.references import HuggingFaceReference


def test_parse_canonical_hf_reference() -> None:
    reference = HuggingFaceReference.parse(
        "hf://model/policyengine/policyengine-us-data@1.73.0/release_manifest.json"
    )

    assert reference == HuggingFaceReference(
        repo_type="model",
        repo_id="policyengine/policyengine-us-data",
        revision="1.73.0",
        path="release_manifest.json",
    )
    assert (
        reference.to_uri()
        == "hf://model/policyengine/policyengine-us-data@1.73.0/release_manifest.json"
    )
    assert (
        reference.download_url()
        == "https://huggingface.co/policyengine/policyengine-us-data/resolve/"
        "1.73.0/release_manifest.json"
    )


def test_parse_dataset_hf_reference() -> None:
    reference = HuggingFaceReference.parse(
        "hf://dataset/policyengine/policyengine-us-data@1.73.0/data/file.h5"
    )

    assert reference.repo_type == "dataset"
    assert reference.repo_id == "policyengine/policyengine-us-data"
    assert reference.revision == "1.73.0"
    assert reference.path == "data/file.h5"
    assert (
        reference.download_url()
        == "https://huggingface.co/datasets/policyengine/policyengine-us-data/"
        "resolve/1.73.0/data/file.h5"
    )


def test_parse_default_model_hf_reference() -> None:
    reference = HuggingFaceReference.parse(
        "hf://policyengine/policyengine-us-data@1.73.0/release_manifest.json"
    )

    assert reference.repo_type == "model"
    assert (
        reference.to_uri()
        == "hf://model/policyengine/policyengine-us-data@1.73.0/release_manifest.json"
    )


def test_parse_legacy_hf_reference() -> None:
    reference = HuggingFaceReference.parse(
        "hf://policyengine/policyengine-us-data/enhanced_cps_2024.h5@1.73.0"
    )

    assert reference.repo_type == "model"
    assert reference.repo_id == "policyengine/policyengine-us-data"
    assert reference.revision == "1.73.0"
    assert reference.path == "enhanced_cps_2024.h5"
    assert (
        reference.to_uri() == "hf://model/policyengine/policyengine-us-data@1.73.0/"
        "enhanced_cps_2024.h5"
    )


@pytest.mark.parametrize(
    "uri",
    [
        "https://huggingface.co/policyengine/policyengine-us-data",
        "hf://policyengine/policyengine-us-data",
        "hf://model/policyengine/policyengine-us-data@1.73.0",
    ],
)
def test_parse_hf_reference_rejects_incomplete_uri(uri: str) -> None:
    with pytest.raises(ValueError):
        HuggingFaceReference.parse(uri)
