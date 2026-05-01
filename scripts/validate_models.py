from __future__ import annotations

from pathlib import Path

from policyengine_bundles.models import (
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
        BundleManifest,
        CountryBundle,
        DataReleaseManifest,
        RuntimeComponentMetadata,
        ValidationReport,
    ):
        schema = model.model_json_schema()
        if "properties" not in schema:
            raise SystemExit(f"{model.__name__} did not export JSON Schema.")


def main() -> int:
    bundle_dirs = iter_bundle_dirs()
    if not bundle_dirs:
        raise SystemExit("No example or release bundle directories found.")

    for bundle_dir in bundle_dirs:
        bundle = load_bundle_directory(bundle_dir)
        print(f"bundle models ok: {bundle.root.relative_to(REPO_ROOT)}")

    validate_component_metadata_contract()
    print("component metadata model ok")

    validate_model_schema_export()
    print("model schema export ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
