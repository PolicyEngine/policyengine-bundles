from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from policyengine_bundles.models import (
    BundleManifest,
    CountryBundle,
    RuntimeComponentMetadata,
    ValidationReport,
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open() as file:
        return json.load(file)


def load_component_metadata(
    payload: Mapping[str, Any],
) -> RuntimeComponentMetadata:
    """Validate dependency-free metadata emitted by a component package."""

    return RuntimeComponentMetadata.model_validate(payload)


@dataclass(frozen=True)
class BundleDirectory:
    root: Path
    manifest: BundleManifest
    countries: dict[str, CountryBundle]
    validation_report: ValidationReport


def load_bundle_directory(bundle_dir: Path | str) -> BundleDirectory:
    """Load and type-check a bundle directory.

    This function intentionally does not perform external reachability,
    checksum, or install validation. It only verifies that the local bundle
    files conform to the canonical model contracts.
    """

    root = Path(bundle_dir)
    manifest = BundleManifest.model_validate(load_json(root / "bundle.json"))
    validation_report = ValidationReport.model_validate(
        load_json(root / manifest.validation_report)
    )
    countries = {
        country_id: CountryBundle.model_validate(load_json(root / manifest_path))
        for country_id, manifest_path in manifest.countries.items()
    }
    return BundleDirectory(
        root=root,
        manifest=manifest,
        countries=countries,
        validation_report=validation_report,
    )
