from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from policyengine_bundles.models import (
    BundleManifest,
    CountryBundle,
    PackagePin,
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
    _validate_bundle_directory_contract(manifest, countries, validation_report)
    return BundleDirectory(
        root=root,
        manifest=manifest,
        countries=countries,
        validation_report=validation_report,
    )


def _validate_bundle_directory_contract(
    manifest: BundleManifest,
    countries: Mapping[str, CountryBundle],
    validation_report: ValidationReport,
) -> None:
    if "policyengine" not in manifest.packages:
        raise ValueError("Bundle packages must include policyengine.")
    if manifest.policyengine.model_dump(exclude_none=True) != manifest.packages[
        "policyengine"
    ].model_dump(exclude_none=True):
        raise ValueError("Bundle policyengine pin must match packages['policyengine'].")
    if manifest.policyengine.version != manifest.bundle_version:
        raise ValueError(
            "Bundle policyengine version "
            f"{manifest.policyengine.version!r} does not match bundle_version "
            f"{manifest.bundle_version!r}."
        )

    if validation_report.bundle_version != manifest.bundle_version:
        raise ValueError(
            "Validation report bundle_version "
            f"{validation_report.bundle_version!r} does not match bundle "
            f"{manifest.bundle_version!r}."
        )

    for profile_name, profile in manifest.profiles.items():
        missing_packages = [
            package_name
            for package_name in profile.packages
            if package_name not in manifest.packages
        ]
        if missing_packages:
            raise ValueError(
                f"Profile {profile_name!r} references unknown packages: "
                f"{', '.join(sorted(missing_packages))}."
            )

        missing_countries = [
            country_id
            for country_id in profile.countries
            if country_id not in countries
        ]
        if missing_countries:
            raise ValueError(
                f"Profile {profile_name!r} references unknown countries: "
                f"{', '.join(sorted(missing_countries))}."
            )

    for country_id, country in countries.items():
        if country.country_id != country_id:
            raise ValueError(
                f"Country manifest key {country_id!r} does not match country_id "
                f"{country.country_id!r}."
            )
        if country.bundle_version != manifest.bundle_version:
            raise ValueError(
                f"Country {country_id!r} bundle_version "
                f"{country.bundle_version!r} does not match bundle "
                f"{manifest.bundle_version!r}."
            )
        _validate_package_matches_manifest(
            manifest=manifest,
            country_id=country_id,
            package=country.model_package,
            field_name="model_package",
        )
        _validate_package_matches_manifest(
            manifest=manifest,
            country_id=country_id,
            package=country.core_package,
            field_name="core_package",
        )


def _validate_package_matches_manifest(
    *,
    manifest: BundleManifest,
    country_id: str,
    package: PackagePin,
    field_name: str,
) -> None:
    manifest_package = manifest.packages.get(package.name)
    if manifest_package is None:
        raise ValueError(
            f"Country {country_id!r} {field_name} references unknown package "
            f"{package.name!r}."
        )
    if manifest_package.model_dump(exclude_none=True) != package.model_dump(
        exclude_none=True
    ):
        raise ValueError(
            f"Country {country_id!r} {field_name} for {package.name!r} does not "
            "match bundle.json packages entry."
        )
