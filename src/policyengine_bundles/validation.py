from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from policyengine_bundles.io import load_json
from policyengine_bundles.models import (
    BundleManifest,
    CountryBundle,
    LegacyBundleManifest,
    LegacyCountryBundle,
    LegacyPackagePin,
    LegacyValidationReport,
    PackagePin,
    ValidationReport,
)

LoadedBundleManifest = BundleManifest | LegacyBundleManifest
LoadedCountryBundle = CountryBundle | LegacyCountryBundle
LoadedPackagePin = PackagePin | LegacyPackagePin
LoadedValidationReport = ValidationReport | LegacyValidationReport


@dataclass(frozen=True)
class BundleDirectory:
    root: Path
    manifest: LoadedBundleManifest
    countries: dict[str, LoadedCountryBundle]
    validation_report: LoadedValidationReport


def load_bundle_directory(bundle_dir: Path | str) -> BundleDirectory:
    """Load and type-check a bundle directory.

    Schema v2 bundles are the active registry contract. Schema v1 bundles are
    supported only as read-only historical artifacts.
    """

    root = Path(bundle_dir)
    manifest_payload = load_json(root / "bundle.json")
    schema_version = manifest_payload.get("schema_version")
    if schema_version == 2:
        return _load_registry_bundle_directory(root, manifest_payload)
    if schema_version == 1:
        return _load_legacy_bundle_directory(root, manifest_payload)
    raise ValueError(
        f"Bundle schema_version must be 1 or 2; got schema_version={schema_version!r}."
    )


def _load_registry_bundle_directory(
    root: Path,
    manifest_payload: dict,
) -> BundleDirectory:
    manifest = BundleManifest.model_validate(manifest_payload)
    _validate_bundle_manifest_paths(manifest)
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


def _load_legacy_bundle_directory(
    root: Path,
    manifest_payload: dict,
) -> BundleDirectory:
    manifest = LegacyBundleManifest.model_validate(manifest_payload)
    _validate_bundle_manifest_paths(manifest)
    validation_report = LegacyValidationReport.model_validate(
        load_json(root / manifest.validation_report)
    )
    countries = {
        country_id: LegacyCountryBundle.model_validate(load_json(root / manifest_path))
        for country_id, manifest_path in manifest.countries.items()
    }
    _validate_legacy_bundle_directory_contract(manifest, countries, validation_report)
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
        if country.compatibility.model_package.model_dump(
            exclude_none=True
        ) != country.model_package.model_dump(exclude_none=True):
            raise ValueError(
                f"Country {country_id!r} compatibility model_package does not match."
            )
        if country.compatibility.core_package.model_dump(
            exclude_none=True
        ) != country.core_package.model_dump(exclude_none=True):
            raise ValueError(
                f"Country {country_id!r} compatibility core_package does not match."
            )
        if (
            country.compatibility.data_package.name != country.data_package.name
            or country.compatibility.data_package.version
            != country.data_package.version
        ):
            raise ValueError(
                f"Country {country_id!r} compatibility data_package does not match."
            )


def _validate_legacy_bundle_directory_contract(
    manifest: LegacyBundleManifest,
    countries: Mapping[str, LegacyCountryBundle],
    validation_report: LegacyValidationReport,
) -> None:
    if "policyengine" not in manifest.packages:
        raise ValueError("Legacy bundle packages must include policyengine.")
    if manifest.policyengine.model_dump(exclude_none=True) != manifest.packages[
        "policyengine"
    ].model_dump(exclude_none=True):
        raise ValueError(
            "Legacy bundle policyengine pin must match packages['policyengine']."
        )
    if manifest.policyengine.version != manifest.bundle_version:
        raise ValueError(
            "Legacy bundle policyengine version "
            f"{manifest.policyengine.version!r} does not match bundle_version "
            f"{manifest.bundle_version!r}."
        )
    if validation_report.bundle_version != manifest.bundle_version:
        raise ValueError(
            "Legacy validation report bundle_version "
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
                f"Legacy profile {profile_name!r} references unknown packages: "
                f"{', '.join(sorted(missing_packages))}."
            )
        missing_countries = [
            country_id
            for country_id in profile.countries
            if country_id not in countries
        ]
        if missing_countries:
            raise ValueError(
                f"Legacy profile {profile_name!r} references unknown countries: "
                f"{', '.join(sorted(missing_countries))}."
            )
        for target_key, install_target in profile.install_targets.items():
            expected_key = _legacy_python_version_key(install_target.python_version)
            if target_key != expected_key:
                raise ValueError(
                    f"Legacy profile {profile_name!r} install target key "
                    f"{target_key!r} does not match python_version "
                    f"{install_target.python_version!r}; expected "
                    f"{expected_key!r}."
                )

    for country_id, country in countries.items():
        if country.country_id != country_id:
            raise ValueError(
                f"Legacy country manifest key {country_id!r} does not match "
                f"country_id {country.country_id!r}."
            )
        if country.bundle_version != manifest.bundle_version:
            raise ValueError(
                f"Legacy country {country_id!r} bundle_version "
                f"{country.bundle_version!r} does not match bundle "
                f"{manifest.bundle_version!r}."
            )
        if country.default_dataset not in country.datasets:
            raise ValueError(
                f"Legacy country {country_id!r} default_dataset "
                f"{country.default_dataset!r} is not present in datasets."
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
    manifest: LoadedBundleManifest,
    country_id: str,
    package: LoadedPackagePin,
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


def _validate_bundle_manifest_paths(manifest: LoadedBundleManifest) -> None:
    for country_id, manifest_path in manifest.countries.items():
        _validate_relative_posix_path(
            manifest_path,
            f"countries[{country_id!r}]",
        )
    _validate_relative_posix_path(manifest.validation_report, "validation_report")


def _validate_relative_posix_path(path: str, field_name: str) -> None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or path in {"", "."}:
        raise ValueError(f"{field_name} must be a bundle-relative POSIX path.")


def _legacy_python_version_key(python_version: str) -> str:
    return "py" + "".join(part for part in python_version.split(".") if part)
