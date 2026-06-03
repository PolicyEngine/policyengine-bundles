from __future__ import annotations

from pathlib import Path

from policyengine_bundles.models import (
    BundleCandidate,
    BundleManifest,
    CountryBundle,
    DataReleaseManifest,
    RuntimeComponentMetadata,
    ValidationReport,
)
from policyengine_bundles.validation import (
    load_bundle_directory,
    load_component_metadata,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOTS = [
    REPO_ROOT / "examples" / "bundles",
    REPO_ROOT / "bundles",
]


def iter_bundle_dirs() -> list[Path]:
    bundle_dirs: list[Path] = []
    for root in BUNDLE_ROOTS:
        if root.exists():
            bundle_dirs.extend(path for path in sorted(root.iterdir()) if path.is_dir())
    return bundle_dirs


def validate_component_metadata_contract() -> None:
    metadata = load_component_metadata(
        {
            "name": "policyengine-core",
            "version": "3.25.3",
            "git_sha": "abc123",
            "wheel_sha256": "0" * 64,
        }
    )
    assert metadata.name == "policyengine-core"


def validate_model_schema_export() -> None:
    for model in (
        BundleCandidate,
        BundleManifest,
        CountryBundle,
        DataReleaseManifest,
        RuntimeComponentMetadata,
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
    bundle_dirs = iter_bundle_dirs()
    if not bundle_dirs:
        raise SystemExit("No example or release bundle directories found.")

    for bundle_dir in bundle_dirs:
        bundle = load_bundle_directory(bundle_dir)
        print(f"bundle models ok: {bundle.root.relative_to(REPO_ROOT)}")

    validate_component_metadata_contract()
    print("component metadata model ok")

    validate_data_release_preservation_contract()
    print("data release preservation model ok")

    validate_model_schema_export()
    print("model schema export ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
