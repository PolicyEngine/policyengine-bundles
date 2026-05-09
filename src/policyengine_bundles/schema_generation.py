from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel

from policyengine_bundles.models import (
    BundleManifest,
    CountryBundle,
    DataReleaseManifest,
    RuntimeComponentMetadata,
    ValidationReport,
)

JsonDict: TypeAlias = dict[str, object]
SchemaModel: TypeAlias = type[BaseModel]

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True)
class SchemaSpec:
    filename: str
    model: SchemaModel
    schema_id: str
    title: str
    description: str


SCHEMA_SPECS: tuple[SchemaSpec, ...] = (
    SchemaSpec(
        filename="bundle.schema.json",
        model=BundleManifest,
        schema_id="https://policyengine.org/schemas/policyengine-bundle.schema.json",
        title="PolicyEngine bundle",
        description=(
            "Top-level manifest that maps one policyengine release to certified "
            "country profiles, package pins, data manifests, and validation evidence."
        ),
    ),
    SchemaSpec(
        filename="country-bundle.schema.json",
        model=CountryBundle,
        schema_id=(
            "https://policyengine.org/schemas/policyengine-country-bundle.schema.json"
        ),
        title="PolicyEngine country bundle",
        description=(
            "Country-specific certification manifest for one PolicyEngine bundle."
        ),
    ),
    SchemaSpec(
        filename="component-runtime-metadata.schema.json",
        model=RuntimeComponentMetadata,
        schema_id=(
            "https://policyengine.org/schemas/"
            "policyengine-component-runtime-metadata.schema.json"
        ),
        title="PolicyEngine component runtime metadata",
        description=(
            "Dependency-free metadata emitted by component packages for bundle "
            "certification."
        ),
    ),
    SchemaSpec(
        filename="data-release-manifest.schema.json",
        model=DataReleaseManifest,
        schema_id=(
            "https://policyengine.org/schemas/"
            "policyengine-data-release-manifest.schema.json"
        ),
        title="PolicyEngine data release manifest",
        description="Published data-package release contract consumed by bundles.",
    ),
    SchemaSpec(
        filename="validation-report.schema.json",
        model=ValidationReport,
        schema_id=(
            "https://policyengine.org/schemas/"
            "policyengine-bundle-validation-report.schema.json"
        ),
        title="PolicyEngine bundle validation report",
        description="Machine-readable validation results for a PolicyEngine bundle.",
    ),
)


def generate_schema(spec: SchemaSpec) -> JsonDict:
    schema = spec.model.model_json_schema(mode="validation")
    schema["$schema"] = JSON_SCHEMA_DIALECT
    schema["$id"] = spec.schema_id
    schema["title"] = spec.title
    schema["description"] = spec.description
    return schema


def generated_schema_documents() -> dict[str, JsonDict]:
    return {spec.filename: generate_schema(spec) for spec in SCHEMA_SPECS}


def write_schema_documents(schema_dir: Path) -> None:
    schema_dir.mkdir(parents=True, exist_ok=True)
    for filename, schema in generated_schema_documents().items():
        path = schema_dir / filename
        with path.open("w") as file:
            json.dump(schema, file, indent=2, sort_keys=True)
            file.write("\n")
