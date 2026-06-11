from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema.validators import validator_for

from policyengine_bundles.models import (
    LegacyBundleCandidate,
    LegacyBundleManifest,
    LegacyCountryBundle,
    LegacyValidationReport,
)
from policyengine_bundles.schema_generation import generated_schema_documents
from policyengine_bundles.validation import load_bundle_directory

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schemas"
BUNDLE_ROOTS = [
    REPO_ROOT / "examples" / "bundles",
    REPO_ROOT / "bundles",
]
CANDIDATE_ROOTS = [
    REPO_ROOT / "examples" / "candidates",
    REPO_ROOT / "candidates",
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open() as file:
        return json.load(file)


def load_schema(path: Path) -> dict[str, Any]:
    schema = load_json(path)
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    return schema


def validate_instance(schema: dict[str, Any], instance_path: Path) -> None:
    validator_cls = validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    instance = load_json(instance_path)
    errors = sorted(validator.iter_errors(instance), key=lambda error: error.path)
    if errors:
        details = "\n".join(
            f"- {'/'.join(str(part) for part in error.path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        )
        raise SystemExit(f"{instance_path} failed validation:\n{details}")


def schema_version(instance_path: Path) -> int:
    instance = load_json(instance_path)
    version = instance.get("schema_version")
    if not isinstance(version, int):
        raise SystemExit(f"{instance_path} missing integer schema_version.")
    return version


def validate_generated_schemas_current() -> None:
    expected = generated_schema_documents()
    actual_schema_paths = {
        path.name: path for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
    }
    if set(actual_schema_paths) != set(expected):
        extra = sorted(set(actual_schema_paths).difference(expected))
        missing = sorted(set(expected).difference(actual_schema_paths))
        raise SystemExit(
            "Schema file set does not match generated Pydantic schemas. "
            f"Extra: {extra}. Missing: {missing}. "
            "Run python scripts/generate_schemas.py."
        )

    for filename, expected_schema in expected.items():
        actual_schema = load_json(actual_schema_paths[filename])
        if actual_schema != expected_schema:
            raise SystemExit(
                f"{actual_schema_paths[filename]} is not generated from the "
                "current Pydantic models. Run python scripts/generate_schemas.py."
            )
        print(
            "schema generation ok: "
            f"{actual_schema_paths[filename].relative_to(REPO_ROOT)}"
        )


def iter_bundle_dirs() -> list[Path]:
    bundle_dirs: list[Path] = []
    for root in BUNDLE_ROOTS:
        if not root.exists():
            continue
        bundle_dirs.extend(path for path in sorted(root.iterdir()) if path.is_dir())
    return bundle_dirs


def iter_candidate_paths() -> list[Path]:
    candidate_paths: list[Path] = []
    for root in CANDIDATE_ROOTS:
        if not root.exists():
            continue
        candidate_paths.extend(sorted(root.glob("*.json")))
    return candidate_paths


def main() -> int:
    validate_generated_schemas_current()

    bundle_schema = load_schema(SCHEMA_DIR / "bundle.schema.json")
    candidate_schema = load_schema(SCHEMA_DIR / "bundle-candidate.schema.json")
    country_schema = load_schema(SCHEMA_DIR / "country-bundle.schema.json")
    validation_schema = load_schema(SCHEMA_DIR / "validation-report.schema.json")

    for schema_path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        load_schema(schema_path)
        print(f"schema ok: {schema_path.relative_to(REPO_ROOT)}")

    candidate_paths = iter_candidate_paths()
    if not candidate_paths:
        raise SystemExit("No example or release bundle candidates found.")
    for candidate_path in candidate_paths:
        if schema_version(candidate_path) == 1:
            LegacyBundleCandidate.model_validate(load_json(candidate_path))
            print(f"legacy candidate ok: {candidate_path.relative_to(REPO_ROOT)}")
            continue
        validate_instance(candidate_schema, candidate_path)
        print(f"candidate ok: {candidate_path.relative_to(REPO_ROOT)}")

    bundle_dirs = iter_bundle_dirs()
    if not bundle_dirs:
        raise SystemExit("No example or release bundle directories found.")

    for bundle_dir in bundle_dirs:
        bundle_path = bundle_dir / "bundle.json"
        validation_path = bundle_dir / "validation-report.json"
        countries_dir = bundle_dir / "countries"

        if not bundle_path.exists():
            raise SystemExit(f"Missing {bundle_path}")
        if not validation_path.exists():
            raise SystemExit(f"Missing {validation_path}")
        if not countries_dir.exists():
            raise SystemExit(f"Missing {countries_dir}")

        if schema_version(bundle_path) == 1:
            LegacyBundleManifest.model_validate(load_json(bundle_path))
            LegacyValidationReport.model_validate(load_json(validation_path))
            print(f"legacy bundle ok: {bundle_path.relative_to(REPO_ROOT)}")
            print(
                f"legacy validation report ok: {validation_path.relative_to(REPO_ROOT)}"
            )

            country_paths = sorted(countries_dir.glob("*.json"))
            if not country_paths:
                raise SystemExit(f"No country manifests under {countries_dir}")
            for country_path in country_paths:
                LegacyCountryBundle.model_validate(load_json(country_path))
                print(f"legacy country ok: {country_path.relative_to(REPO_ROOT)}")
            load_bundle_directory(bundle_dir)
            continue

        validate_instance(bundle_schema, bundle_path)
        validate_instance(validation_schema, validation_path)
        print(f"bundle ok: {bundle_path.relative_to(REPO_ROOT)}")
        print(f"validation report ok: {validation_path.relative_to(REPO_ROOT)}")

        country_paths = sorted(countries_dir.glob("*.json"))
        if not country_paths:
            raise SystemExit(f"No country manifests under {countries_dir}")
        for country_path in country_paths:
            validate_instance(country_schema, country_path)
            print(f"country ok: {country_path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
