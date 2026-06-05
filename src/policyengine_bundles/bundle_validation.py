from __future__ import annotations

import hashlib
import json
import os
import sys
import tomllib
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from policyengine_bundles.io import load_json, write_json
from policyengine_bundles.lockfiles import CommandRunner, run_command
from policyengine_bundles.models import (
    CountryBundle,
    DataArtifact,
    InstallTarget,
    Profile,
    ValidationCheck,
    ValidationReport,
)
from policyengine_bundles.python_versions import (
    metadata_python_versions,
    python_version_key_map,
)
from policyengine_bundles.references import HuggingFaceReference, hugging_face_token
from policyengine_bundles.validation import BundleDirectory, load_bundle_directory

IMPORT_NAMES = {
    "policyengine": "policyengine",
    "policyengine-core": "policyengine_core",
    "policyengine-us": "policyengine_us",
    "policyengine-uk": "policyengine_uk",
}


@dataclass(frozen=True)
class ContentVerification:
    sha256: str
    size_bytes: int


ContentVerifier = Callable[[str], ContentVerification]


@dataclass(frozen=True)
class RuntimeInstallTarget:
    python_version: str
    constraints: str
    lockfile: str | None


def validate_bundle(
    bundle_dir: Path | str,
    *,
    runner: CommandRunner = run_command,
    content_verifier: ContentVerifier | None = None,
    artifact_verifier: ContentVerifier | None = None,
    verify_data: bool = True,
    validate_runtime: bool = True,
) -> ValidationReport:
    if content_verifier is not None and artifact_verifier is not None:
        raise ValueError("Pass either content_verifier or artifact_verifier, not both.")
    root = Path(bundle_dir)
    try:
        bundle = load_bundle_directory(root)
    except Exception as exc:
        report, report_path = _bundle_load_failure_report(
            root,
            exc,
            verify_data=verify_data,
            validate_runtime=validate_runtime,
        )
        if root.exists() and root.is_dir():
            write_json(report_path, report.model_dump(exclude_none=True))
        return report

    selected_profiles = list(bundle.manifest.profiles)
    resolved_content_verifier = (
        content_verifier or artifact_verifier or verify_content_uri
    )
    checks: list[ValidationCheck] = []
    if verify_data:
        checks.extend(
            _validate_data_contracts(
                bundle=bundle,
                profiles=selected_profiles,
                content_verifier=resolved_content_verifier,
            )
        )
    else:
        checks.extend(
            _skipped_data_contract_checks(
                bundle=bundle,
                profiles=selected_profiles,
            )
        )
    for profile_name in selected_profiles:
        profile = bundle.manifest.profiles[profile_name]
        if not validate_runtime:
            checks.append(
                ValidationCheck(
                    name="runtime_validation",
                    status="skipped",
                    profile=profile_name,
                    details={
                        "reason": "Runtime validation disabled by caller.",
                    },
                )
            )
            continue
        install_target_coverage = _validate_install_target_coverage(
            bundle=bundle,
            profile_name=profile_name,
            profile=profile,
        )
        checks.append(install_target_coverage)
        if install_target_coverage.status == "failed":
            continue
        install_targets = _selected_install_targets(profile=profile)
        for target_key, install_target in install_targets:
            checks.extend(
                _validate_profile_runtime(
                    bundle=bundle,
                    profile_name=profile_name,
                    target_key=target_key,
                    install_target=install_target,
                    runner=runner,
                )
            )

    report = ValidationReport(
        schema_version=1,
        bundle_version=bundle.manifest.bundle_version,
        generated_at=_now_timestamp(),
        status=_overall_status(checks),
        checks=checks,
        metadata={
            "generated_by": "scripts/validate_bundle.py",
            "validation_scope": (
                "full" if verify_data and validate_runtime else "partial"
            ),
            "data_validation_mode": (
                "release_manifest_and_artifact_metadata" if verify_data else "skipped"
            ),
            "verify_data": verify_data,
            "validate_runtime": validate_runtime,
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
    *,
    verify_data: bool,
    validate_runtime: bool,
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
        schema_version=1,
        bundle_version=bundle_version,
        generated_at=_now_timestamp(),
        status="failed",
        checks=checks,
        metadata={
            "generated_by": "scripts/validate_bundle.py",
            "validation_scope": "partial",
            "data_validation_mode": "not_run_bundle_load_failed",
            "verify_data": verify_data,
            "validate_runtime": validate_runtime,
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


def current_python_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform.startswith(("win32", "cygwin")):
        return "windows"
    return sys.platform


def _selected_install_targets(
    *,
    profile: Profile,
) -> list[tuple[str, RuntimeInstallTarget]]:
    return [
        (target_key, _runtime_install_target(target))
        for target_key, target in sorted(profile.install_targets.items())
    ]


def _validate_install_target_coverage(
    *,
    bundle: BundleDirectory,
    profile_name: str,
    profile: Profile,
) -> ValidationCheck:
    declared_python_versions = metadata_python_versions(bundle.manifest.metadata)
    if declared_python_versions is None:
        return ValidationCheck(
            name="install_targets_complete",
            status="failed",
            profile=profile_name,
            details={
                "reason": (
                    "Bundle metadata.python_versions is required before runtime "
                    "validation."
                )
            },
        )

    expected_targets = python_version_key_map(
        declared_python_versions,
        field_name="metadata.python_versions",
    )
    expected_keys = set(expected_targets)
    actual_keys = set(profile.install_targets)
    missing_keys = sorted(expected_keys.difference(actual_keys))
    extra_keys = sorted(actual_keys.difference(expected_keys))
    failures: list[str] = []
    if missing_keys:
        failures.append(
            "missing install targets for declared Python versions: "
            + ", ".join(
                f"{target_key} ({expected_targets[target_key]})"
                for target_key in missing_keys
            )
        )
    if extra_keys:
        failures.append(
            "install targets are not declared in metadata.python_versions: "
            + ", ".join(extra_keys)
        )

    return ValidationCheck(
        name="install_targets_complete",
        status="failed" if failures else "passed",
        profile=profile_name,
        details={
            "declared_python_versions": declared_python_versions,
            "install_targets": sorted(actual_keys),
            "failures": failures,
        }
        if failures
        else {
            "declared_python_versions": declared_python_versions,
            "install_targets": sorted(actual_keys),
        },
    )


def _runtime_install_target(target: InstallTarget) -> RuntimeInstallTarget:
    return RuntimeInstallTarget(
        python_version=target.python_version,
        constraints=target.constraints,
        lockfile=target.lockfile,
    )


def _validate_data_contracts(
    bundle: BundleDirectory,
    profiles: Sequence[str],
    content_verifier: ContentVerifier,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for profile_name in profiles:
        profile = bundle.manifest.profiles[profile_name]
        for country_id in profile.countries:
            country = bundle.countries[country_id]
            failures: list[str] = []
            if country.default_dataset not in country.datasets:
                failures.append(
                    f"default_dataset {country.default_dataset!r} missing from datasets"
                )
            _verify_release_manifest(
                bundle=bundle,
                country=country,
                content_verifier=content_verifier,
                failures=failures,
            )
            for artifact_key, artifact in country.datasets.items():
                _validate_artifact_metadata(
                    country=country,
                    artifact_key=artifact_key,
                    artifact=artifact,
                    failures=failures,
                )
            checks.append(
                ValidationCheck(
                    name="data_release_manifest_contract",
                    status="failed" if failures else "passed",
                    profile=profile_name,
                    country=country_id,
                    details={"failures": failures} if failures else {},
                )
            )
    return checks


def _skipped_data_contract_checks(
    bundle: BundleDirectory,
    profiles: Sequence[str],
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for profile_name in profiles:
        profile = bundle.manifest.profiles[profile_name]
        for country_id in profile.countries:
            checks.append(
                ValidationCheck(
                    name="data_release_manifest_contract",
                    status="skipped",
                    profile=profile_name,
                    country=country_id,
                    details={
                        "reason": (
                            "Release manifest and artifact metadata validation "
                            "disabled by caller."
                        ),
                    },
                )
            )
    return checks


def _verify_release_manifest(
    *,
    bundle: BundleDirectory,
    country: CountryBundle,
    content_verifier: ContentVerifier,
    failures: list[str],
) -> None:
    expected_sha256 = (
        country.artifact_release.release_manifest_sha256
        if country.artifact_release
        else country.metadata.get("input_release_manifest_sha256")
    )
    if not isinstance(expected_sha256, str):
        failures.append(f"{country.country_id} missing release manifest sha256")
        return

    release_manifest_uri = (
        country.artifact_release.release_manifest_uri
        if country.artifact_release is not None
        else None
    )
    if country.artifact_release is not None and release_manifest_uri is None:
        local_manifest_path = _bundle_local_release_manifest_path(bundle, country)
        if local_manifest_path is None:
            failures.append(
                f"{country.country_id} embedded release manifest missing at "
                f"{country.data_package.release_manifest_path}"
            )
            return
        try:
            verification = _hash_file(local_manifest_path)
        except Exception as exc:
            failures.append(
                f"{country.country_id} embedded release manifest could not be read: "
                f"{exc}"
            )
            return
        if verification.sha256 != expected_sha256:
            failures.append(
                f"{country.country_id} release manifest sha256 mismatch: expected "
                f"{expected_sha256}, got {verification.sha256}"
            )
        return

    if not isinstance(release_manifest_uri, str):
        release_manifest_uri = country.metadata.get("source_release_manifest_uri")
    if not isinstance(release_manifest_uri, str):
        release_manifest_uri = country.metadata.get("input_release_manifest_uri")
    if not isinstance(release_manifest_uri, str):
        failures.append(f"{country.country_id} missing release manifest URI")
        return
    try:
        verification = content_verifier(release_manifest_uri)
    except Exception as exc:
        failures.append(
            f"{country.country_id} release manifest could not be read: {exc}"
        )
        return
    if verification.sha256 != expected_sha256:
        failures.append(
            f"{country.country_id} release manifest sha256 mismatch: expected "
            f"{expected_sha256}, got {verification.sha256}"
        )


def _validate_artifact_metadata(
    *,
    country: CountryBundle,
    artifact_key: str,
    artifact: DataArtifact,
    failures: list[str],
) -> None:
    if artifact.status in {"certified", "partially_certified", "hash_pinned"}:
        if not artifact.sha256:
            failures.append(f"{artifact_key} missing sha256")
    if _artifact_uri(country, artifact) is None:
        failures.append(f"{artifact_key} missing artifact URI")


def _bundle_local_release_manifest_path(
    bundle: BundleDirectory,
    country: CountryBundle,
) -> Path | None:
    path = PurePosixPath(country.data_package.release_manifest_path)
    if path.is_absolute() or ".." in path.parts:
        return None
    candidate = bundle.root.joinpath(*path.parts)
    if candidate.exists():
        return candidate
    return None


def _artifact_uri(country: CountryBundle, artifact: DataArtifact) -> str | None:
    if artifact.uri:
        return artifact.uri
    if artifact.path and artifact.repo_id and artifact.revision:
        repo_type = (
            artifact.metadata.get("repo_type")
            or (
                country.artifact_release.repo_type
                if country.artifact_release
                else country.data_package.repo_type
            )
            or "model"
        )
        return (
            f"hf://{repo_type}/{artifact.repo_id}@{artifact.revision}/{artifact.path}"
        )
    return None


def _validate_profile_runtime(
    *,
    bundle: BundleDirectory,
    profile_name: str,
    target_key: str,
    install_target: RuntimeInstallTarget,
    runner: CommandRunner,
) -> list[ValidationCheck]:
    profile = bundle.manifest.profiles[profile_name]
    runtime_package_names = [
        name
        for name in profile.packages
        if not bundle.manifest.packages[name].is_bundle_carrier
    ]
    checks: list[ValidationCheck] = []
    checks.append(
        _validate_lockfile(
            bundle=bundle,
            profile_name=profile_name,
            python_version=install_target.python_version,
            target_key=target_key,
            lockfile_path=install_target.lockfile,
        )
    )

    constraints_file = bundle.root / install_target.constraints
    if not constraints_file.exists():
        checks.append(
            ValidationCheck(
                name="constraints_present",
                status="failed",
                profile=profile_name,
                python_version=install_target.python_version,
                details={
                    "target": target_key,
                    "path": install_target.constraints,
                    "validated_on_platform": current_python_platform(),
                },
            )
        )
        return checks
    checks.append(
        ValidationCheck(
            name="constraints_present",
            status="passed",
            profile=profile_name,
            python_version=install_target.python_version,
            details={
                "target": target_key,
                "path": install_target.constraints,
                "validated_on_platform": current_python_platform(),
            },
        )
    )

    with TemporaryDirectory() as temp_dir:
        venv = Path(temp_dir) / "venv"
        python = venv / ("Scripts/python.exe" if _is_windows() else "bin/python")
        commands = [
            (
                "create_venv",
                [
                    "uv",
                    "venv",
                    "--python",
                    install_target.python_version,
                    str(venv),
                ],
            ),
            (
                "install_constraints",
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "-r",
                    str(constraints_file),
                ],
            ),
            (
                "verify_direct_package_versions",
                [
                    str(python),
                    "-c",
                    _package_version_check_code(bundle, runtime_package_names),
                ],
            ),
            (
                "import_smoke",
                [
                    str(python),
                    "-c",
                    _import_smoke_code(runtime_package_names),
                ],
            ),
        ]
        commands.extend(
            (
                f"{country_id}_household_smoke",
                [
                    str(python),
                    "-c",
                    _household_smoke_code(
                        country_id,
                        use_bundle_carrier="policyengine" in runtime_package_names,
                    ),
                ],
            )
            for country_id in profile.countries
            if country_id in {"us", "uk"}
        )
        for name, command in commands:
            checks.append(
                _run_check(
                    name=name,
                    command=command,
                    profile=profile_name,
                    python_version=install_target.python_version,
                    target_key=target_key,
                    runner=runner,
                )
            )
    return checks


def _validate_lockfile(
    *,
    bundle: BundleDirectory,
    profile_name: str,
    python_version: str,
    target_key: str,
    lockfile_path: str | None,
) -> ValidationCheck:
    validated_on_platform = current_python_platform()
    if lockfile_path is None:
        return ValidationCheck(
            name="lockfile_present",
            status="failed",
            profile=profile_name,
            python_version=python_version,
            details={
                "target": target_key,
                "reason": "target has no lockfile",
                "validated_on_platform": validated_on_platform,
            },
        )
    path = bundle.root / lockfile_path
    if not path.exists():
        return ValidationCheck(
            name="lockfile_present",
            status="failed",
            profile=profile_name,
            python_version=python_version,
            details={
                "target": target_key,
                "path": lockfile_path,
                "reason": "lockfile does not exist",
                "validated_on_platform": validated_on_platform,
            },
        )
    try:
        tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        return ValidationCheck(
            name="lockfile_present",
            status="failed",
            profile=profile_name,
            python_version=python_version,
            details={
                "target": target_key,
                "path": lockfile_path,
                "reason": str(exc),
                "validated_on_platform": validated_on_platform,
            },
        )
    return ValidationCheck(
        name="lockfile_present",
        status="passed",
        profile=profile_name,
        python_version=python_version,
        details={
            "target": target_key,
            "path": lockfile_path,
            "validated_on_platform": validated_on_platform,
        },
    )


def _run_check(
    *,
    name: str,
    command: list[str],
    profile: str,
    python_version: str,
    target_key: str,
    runner: CommandRunner,
) -> ValidationCheck:
    started_at = _now_timestamp()
    validated_on_platform = current_python_platform()
    try:
        runner(command)
    except Exception as exc:
        return ValidationCheck(
            name=name,
            status="failed",
            profile=profile,
            python_version=python_version,
            command=" ".join(command),
            started_at=started_at,
            ended_at=_now_timestamp(),
            details={
                "target": target_key,
                "validated_on_platform": validated_on_platform,
                "error": str(exc),
            },
        )
    return ValidationCheck(
        name=name,
        status="passed",
        profile=profile,
        python_version=python_version,
        command=" ".join(command),
        started_at=started_at,
        ended_at=_now_timestamp(),
        details={
            "target": target_key,
            "validated_on_platform": validated_on_platform,
        },
    )


def _package_version_check_code(
    bundle: BundleDirectory,
    package_names: Sequence[str],
) -> str:
    expected = {
        name: bundle.manifest.packages[name].version
        for name in package_names
        if bundle.manifest.packages[name].version is not None
    }
    return (
        "import importlib.metadata as md\n"
        f"expected = {json.dumps(expected, sort_keys=True)}\n"
        "for name, version in expected.items():\n"
        "    actual = md.version(name)\n"
        "    assert actual == version, f'{name}: expected {version}, got {actual}'\n"
    )


def _import_smoke_code(package_names: Sequence[str]) -> str:
    imports = [IMPORT_NAMES[name] for name in package_names if name in IMPORT_NAMES]
    return "\n".join(f"import {module}" for module in imports) + "\n"


def _household_smoke_code(country_id: str, *, use_bundle_carrier: bool) -> str:
    if country_id == "us":
        if not use_bundle_carrier:
            return (
                "from policyengine_us import Simulation\n"
                "simulation = Simulation(situation={"
                "'people': {'person': {'age': {'2026': 35}, "
                "'employment_income': {'2026': 1_000}}}, "
                "'households': {'household': {'members': ['person'], "
                "'state_code': {'2026': 'CA'}}}, "
                "'tax_units': {'tax_unit': {'members': ['person'], "
                "'filing_status': {'2026': 'SINGLE'}}}, "
                "'spm_units': {'spm_unit': {'members': ['person']}}, "
                "'families': {'family': {'members': ['person']}}, "
                "'marital_units': {'marital_unit': {'members': ['person']}}, "
                "})\n"
                "simulation.calculate('age', '2026')\n"
            )
        return (
            "import policyengine as pe\n"
            "pe.us.calculate_household("
            "people=[{'age': 35}], "
            "tax_unit={'filing_status': 'SINGLE'}, "
            "year=2026"
            ")\n"
        )
    if country_id == "uk":
        if not use_bundle_carrier:
            return (
                "from policyengine_uk import Simulation\n"
                "simulation = Simulation(situation={"
                "'people': {'person': {'age': {'2026': 35}, "
                "'employment_income': {'2026': 0}}}, "
                "'benunits': {'benunit': {'members': ['person']}}, "
                "'households': {'household': {'members': ['person']}}, "
                "})\n"
                "simulation.calculate('age', '2026')\n"
            )
        return (
            "import policyengine as pe\n"
            "pe.uk.calculate_household(people=[{'age': 35}], year=2026)\n"
        )
    raise ValueError(f"Unsupported household smoke country: {country_id}")


def _overall_status(checks: Sequence[ValidationCheck]) -> str:
    if any(check.status == "failed" for check in checks):
        return "failed"
    if any(check.status == "passed" for check in checks):
        return "passed"
    return "skipped"


def _now_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_windows() -> bool:
    return os.name == "nt"


def verify_content_uri(uri: str) -> ContentVerification:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        return _hash_file(path)
    if parsed.scheme == "hf":
        return _hash_url(HuggingFaceReference.parse(uri).download_url())
    raise ValueError(f"Unsupported artifact URI scheme: {uri!r}.")


def _hash_file(path: Path) -> ContentVerification:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    return ContentVerification(sha256=digest.hexdigest(), size_bytes=size_bytes)


def _hash_url(url: str) -> ContentVerification:
    digest = hashlib.sha256()
    size_bytes = 0
    request = urllib.request.Request(url)
    token = hugging_face_token()
    if token and "huggingface.co" in urllib.parse.urlparse(url).netloc:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=300) as response:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            size_bytes += len(chunk)
    return ContentVerification(sha256=digest.hexdigest(), size_bytes=size_bytes)
