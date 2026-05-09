from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema.validators import validator_for

from policyengine_bundles.schema_generation import generated_schema_documents

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schemas"
BUNDLE_ROOTS = [
    REPO_ROOT / "examples" / "bundles",
    REPO_ROOT / "bundles",
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


def main() -> int:
    validate_generated_schemas_current()

    bundle_schema = load_schema(SCHEMA_DIR / "bundle.schema.json")
    country_schema = load_schema(SCHEMA_DIR / "country-bundle.schema.json")
    validation_schema = load_schema(SCHEMA_DIR / "validation-report.schema.json")

    for schema_path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        load_schema(schema_path)
        print(f"schema ok: {schema_path.relative_to(REPO_ROOT)}")

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
