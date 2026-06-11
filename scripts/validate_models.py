from __future__ import annotations

import json
from pathlib import Path

from policyengine_bundles.models import (
    BundleCandidate,
    BundleManifest,
    CountryBundle,
    DataReleaseManifest,
    LegacyBundleCandidate,
    ValidationReport,
)
from policyengine_bundles.validation import load_bundle_directory

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOTS = [
    REPO_ROOT / "examples" / "bundles",
    REPO_ROOT / "bundles",
]
CANDIDATE_ROOTS = [
    REPO_ROOT / "examples" / "candidates",
    REPO_ROOT / "candidates",
]


def iter_bundle_dirs() -> list[Path]:
    bundle_dirs: list[Path] = []
    for root in BUNDLE_ROOTS:
        if root.exists():
            bundle_dirs.extend(path for path in sorted(root.iterdir()) if path.is_dir())
    return bundle_dirs


def iter_candidate_paths() -> list[Path]:
    candidate_paths: list[Path] = []
    for root in CANDIDATE_ROOTS:
        if root.exists():
            candidate_paths.extend(sorted(root.glob("*.json")))
    return candidate_paths


def validate_candidate_model(candidate_path: Path) -> None:
    payload = candidate_path.read_text()
    data = json.loads(payload)
    schema_version = data.get("schema_version")
    if schema_version == 1:
        LegacyBundleCandidate.model_validate_json(payload)
        print(f"legacy candidate model ok: {candidate_path.relative_to(REPO_ROOT)}")
        return
    if schema_version != 2:
        raise SystemExit(
            f"{candidate_path.relative_to(REPO_ROOT)} has unsupported "
            f"candidate schema_version={schema_version!r}."
        )
    BundleCandidate.model_validate_json(payload)
    print(f"candidate model ok: {candidate_path.relative_to(REPO_ROOT)}")


def validate_model_schema_export() -> None:
    for model in (
        BundleCandidate,
        BundleManifest,
        CountryBundle,
        DataReleaseManifest,
        ValidationReport,
    ):
        schema = model.model_json_schema()
        if "properties" not in schema:
            raise SystemExit(f"{model.__name__} did not export JSON Schema.")


def validate_data_release_preservation_contract() -> None:
    manifest = DataReleaseManifest.model_validate(
        {
            "schema_version": 1,
            "data_package": {
                "name": "policyengine-us-data",
                "version": "1.85.2",
            },
            "artifacts": {
                "enhanced_cps_2024": {
                    "kind": "microdata",
                    "path": "enhanced_cps_2024.h5",
                    "repo_id": "policyengine/policyengine-us-data",
                    "revision": "1.85.2",
                    "sha256": "a" * 64,
                    "preservation_mirrors": [
                        {
                            "kind": "zenodo",
                            "url": "https://zenodo.org/records/10000000/files/enhanced_cps_2024.h5",
                            "doi": "10.5281/zenodo.10000000",
                            "sha256": "a" * 64,
                        }
                    ],
                }
            },
            "preservation_dois": ["10.5281/zenodo.10000000"],
        }
    )
    assert manifest.preservation_dois == ["10.5281/zenodo.10000000"]


def main() -> int:
    candidate_paths = iter_candidate_paths()
    if not candidate_paths:
        raise SystemExit("No example or release bundle candidates found.")
    for candidate_path in candidate_paths:
        validate_candidate_model(candidate_path)

    bundle_dirs = iter_bundle_dirs()
    if not bundle_dirs:
        raise SystemExit("No example or release bundle directories found.")

    for bundle_dir in bundle_dirs:
        bundle = load_bundle_directory(bundle_dir)
        print(f"bundle models ok: {bundle.root.relative_to(REPO_ROOT)}")

    validate_data_release_preservation_contract()
    print("data release preservation model ok")

    validate_model_schema_export()
    print("model schema export ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
