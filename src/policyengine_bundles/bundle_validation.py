from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from policyengine_bundles.io import load_json, write_json
from policyengine_bundles.models import (
    CountryBundle,
    DataArtifact,
    PackagePin,
    ValidationCheck,
    ValidationReport,
)
from policyengine_bundles.validation import BundleDirectory, load_bundle_directory


def _now_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_bundle(bundle_dir: Path | str) -> ValidationReport:
    root = Path(bundle_dir)
    try:
        bundle = load_bundle_directory(root)
    except Exception as exc:
        report, report_path = _bundle_load_failure_report(root, exc)
        if root.exists() and root.is_dir():
            write_json(report_path, report.model_dump(exclude_none=True))
        return report

    checks: list[ValidationCheck] = [
        ValidationCheck(
            name="bundle_directory_contract",
            status="passed",
            details={"bundle_dir": str(bundle.root)},
        )
    ]
    checks.extend(_validate_package_pins(bundle))
    for country_id, country in sorted(bundle.countries.items()):
        checks.extend(_validate_country_bundle(country_id, country))

    report = ValidationReport(
        schema_version=2,
        bundle_version=bundle.manifest.bundle_version,
        generated_at=_now_timestamp(),
        status=_overall_status(checks),
        checks=checks,
        metadata={
            "generated_by": "scripts/validate_bundle.py",
            "validation_kind": "registry",
        },
    )
    write_json(
        bundle.root / bundle.manifest.validation_report,
        report.model_dump(exclude_none=True),
    )
    load_bundle_directory(bundle.root)
    return report


def _bundle_load_failure_report(
    root: Path,
    error: Exception,
) -> tuple[ValidationReport, Path]:
    bundle_version, report_path, context = _bundle_failure_context(root)
    checks = [
        ValidationCheck(
            name="bundle_directory_contract",
            status="failed",
            details={
                **context,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
    ]
    report = ValidationReport(
        schema_version=2,
        bundle_version=bundle_version,
        generated_at=_now_timestamp(),
        status="failed",
        checks=checks,
        metadata={
            "generated_by": "scripts/validate_bundle.py",
            "validation_kind": "registry",
        },
    )
    return report, report_path


def _bundle_failure_context(root: Path) -> tuple[str, Path, dict[str, Any]]:
    bundle_version = "unknown"
    report_path = root / "validation-report.json"
    context: dict[str, Any] = {"bundle_dir": str(root)}
    try:
        payload = load_json(root / "bundle.json")
    except Exception as exc:
        context["bundle_json_error"] = f"{type(exc).__name__}: {exc}"
        return bundle_version, report_path, context

    if not isinstance(payload, dict):
        context["bundle_json_error"] = "bundle.json must contain a JSON object."
        return bundle_version, report_path, context

    raw_bundle_version = payload.get("bundle_version")
    if isinstance(raw_bundle_version, str) and raw_bundle_version:
        bundle_version = raw_bundle_version
    else:
        context["bundle_version_error"] = "bundle.json missing string bundle_version."

    raw_report_path = payload.get("validation_report")
    if isinstance(raw_report_path, str):
        parsed = PurePosixPath(raw_report_path)
        if (
            not parsed.is_absolute()
            and ".." not in parsed.parts
            and raw_report_path not in {"", "."}
        ):
            report_path = root.joinpath(*parsed.parts)
        else:
            context["validation_report_path_error"] = (
                "bundle.json validation_report must be a bundle-relative POSIX path."
            )
    else:
        context["validation_report_path_error"] = (
            "bundle.json missing string validation_report."
        )

    return bundle_version, report_path, context


def _validate_package_pins(bundle: BundleDirectory) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for package_name, pin in sorted(bundle.manifest.packages.items()):
        checks.append(_validate_package_pin(package_name, pin))
    return checks


def _validate_package_pin(package_name: str, pin: PackagePin) -> ValidationCheck:
    failures: list[str] = []
    if package_name != pin.name:
        failures.append(f"package key {package_name!r} does not match pin name.")
    if not pin.version:
        failures.append("pin is missing an exact version.")
    if pin.resolution_status != "pinned":
        failures.append("resolution_status must be 'pinned'.")
    if not pin.is_bundle_carrier:
        if pin.sha256 is None:
            failures.append("non-carrier pins must include a wheel sha256.")
        if pin.wheel_url is None and pin.source == "pypi":
            failures.append("PyPI pins must include a wheel_url.")

    return ValidationCheck(
        name="package_pin",
        status="failed" if failures else "passed",
        details={
            "package": package_name,
            "version": pin.version,
            "failures": failures,
        },
    )


def _validate_country_bundle(
    country_id: str,
    country: CountryBundle,
) -> list[ValidationCheck]:
    checks = [
        _validate_compatibility_assertion(country_id, country),
        _validate_release_manifest_provenance(country_id, country),
        _validate_default_dataset(country_id, country),
    ]
    for artifact_key, artifact in sorted(country.datasets.items()):
        checks.append(_validate_artifact_metadata(country_id, artifact_key, artifact))
    return checks


def _validate_compatibility_assertion(
    country_id: str,
    country: CountryBundle,
) -> ValidationCheck:
    failures: list[str] = []
    compatibility = country.compatibility
    if compatibility.basis != "bundle_candidate":
        failures.append("compatibility basis must be bundle_candidate.")
    if compatibility.model_package != country.model_package:
        failures.append("compatibility model_package does not match country package.")
    if compatibility.core_package != country.core_package:
        failures.append("compatibility core_package does not match country package.")
    if compatibility.data_package.name != country.data_package.name:
        failures.append("compatibility data_package name does not match.")
    if compatibility.data_package.version != country.data_package.version:
        failures.append("compatibility data_package version does not match.")
    if not compatibility.release_manifest_uri:
        failures.append("compatibility must record release_manifest_uri.")
    if not compatibility.release_manifest_sha256:
        failures.append("compatibility must record release_manifest_sha256.")

    return ValidationCheck(
        name="compatibility_assertion",
        status="failed" if failures else "passed",
        country=country_id,
        details={
            "basis": compatibility.basis,
            "model_package": country.model_package.name,
            "model_package_version": country.model_package.version,
            "data_package": country.data_package.name,
            "data_package_version": country.data_package.version,
            "failures": failures,
        },
    )


def _validate_release_manifest_provenance(
    country_id: str,
    country: CountryBundle,
) -> ValidationCheck:
    failures: list[str] = []
    if not country.artifact_release.release_manifest_uri:
        failures.append("artifact_release must record release_manifest_uri.")
    if not country.artifact_release.release_manifest_sha256:
        failures.append("artifact_release must record release_manifest_sha256.")
    if (
        country.artifact_release.release_manifest_uri
        != country.compatibility.release_manifest_uri
    ):
        failures.append("release_manifest_uri differs from compatibility assertion.")
    if (
        country.artifact_release.release_manifest_sha256
        != country.compatibility.release_manifest_sha256
    ):
        failures.append("release_manifest_sha256 differs from compatibility assertion.")

    return ValidationCheck(
        name="release_manifest_provenance",
        status="failed" if failures else "passed",
        country=country_id,
        details={
            "release_manifest_uri": country.artifact_release.release_manifest_uri,
            "release_manifest_sha256": (
                country.artifact_release.release_manifest_sha256
            ),
            "failures": failures,
        },
    )


def _validate_default_dataset(
    country_id: str,
    country: CountryBundle,
) -> ValidationCheck:
    failures: list[str] = []
    if country.default_dataset not in country.datasets:
        failures.append("default_dataset must reference an entry in datasets.")
    if not country.datasets:
        failures.append("country must include at least one dataset artifact.")

    return ValidationCheck(
        name="default_dataset",
        status="failed" if failures else "passed",
        country=country_id,
        details={
            "default_dataset": country.default_dataset,
            "dataset_keys": sorted(country.datasets),
            "failures": failures,
        },
    )


def _validate_artifact_metadata(
    country_id: str,
    artifact_key: str,
    artifact: DataArtifact,
) -> ValidationCheck:
    failures: list[str] = []
    if artifact.uri is None and not (
        artifact.path and artifact.repo_id and artifact.revision
    ):
        failures.append("artifact must identify content by uri or path/repo/revision.")
    if artifact.status in {"certified", "partially_certified", "hash_pinned"}:
        if artifact.sha256 is None:
            failures.append("certified/hash-pinned artifact must include sha256.")
    if artifact.status in {"unverified", "unavailable"}:
        if artifact.missing_reason is None:
            failures.append("unverified/unavailable artifact must include reason.")

    return ValidationCheck(
        name="data_artifact_metadata",
        status="failed" if failures else "passed",
        country=country_id,
        artifact=artifact_key,
        details={
            "kind": artifact.kind,
            "status": artifact.status,
            "has_uri": artifact.uri is not None,
            "has_path_reference": bool(
                artifact.path and artifact.repo_id and artifact.revision
            ),
            "has_sha256": artifact.sha256 is not None,
            "failures": failures,
        },
    )


def _overall_status(checks: list[ValidationCheck]) -> str:
    if any(check.status == "failed" for check in checks):
        return "failed"
    if any(check.status == "skipped" for check in checks):
        return "skipped"
    return "passed"
