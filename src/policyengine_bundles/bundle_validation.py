from __future__ import annotations

import hashlib
import json
import os
import tomllib
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from policyengine_bundles.generation import write_json
from policyengine_bundles.lockfiles import CommandRunner, run_command
from policyengine_bundles.models import (
    CountryBundle,
    DataArtifact,
    ValidationCheck,
    ValidationReport,
)
from policyengine_bundles.validation import BundleDirectory, load_bundle_directory

IMPORT_NAMES = {
    "policyengine": "policyengine",
    "policyengine-core": "policyengine_core",
    "policyengine-us": "policyengine_us",
    "policyengine-uk": "policyengine_uk",
}


@dataclass(frozen=True)
class ArtifactVerification:
    sha256: str
    size_bytes: int


ArtifactVerifier = Callable[[str], ArtifactVerification]


def validate_bundle(
    bundle_dir: Path | str,
    *,
    profiles: Sequence[str] | None = None,
    python_versions: Sequence[str] | None = None,
    runner: CommandRunner = run_command,
    artifact_verifier: ArtifactVerifier | None = None,
) -> ValidationReport:
    bundle = load_bundle_directory(bundle_dir)
    selected_profiles = _selected_profiles(
        available_profiles=list(bundle.manifest.profiles),
        requested_profiles=profiles,
    )
    resolved_artifact_verifier = artifact_verifier or verify_artifact_uri
    checks: list[ValidationCheck] = []
    checks.extend(
        _validate_data_contracts(
            bundle=bundle,
            profiles=selected_profiles,
            artifact_verifier=resolved_artifact_verifier,
        )
    )
    for profile_name in selected_profiles:
        profile = bundle.manifest.profiles[profile_name]
        python_keys = _selected_python_keys(profile.constraints, python_versions)
        if not python_keys:
            checks.append(
                ValidationCheck(
                    name="install_artifacts_present",
                    status="failed",
                    profile=profile_name,
                    details={
                        "reason": (
                            "Profile has no constraints. Run "
                            "scripts/solve_lockfiles.py before runtime validation."
                        )
                    },
                )
            )
            continue
        for python_key in python_keys:
            python_version = python_version_from_key(python_key)
            checks.extend(
                _validate_profile_runtime(
                    bundle=bundle,
                    profile_name=profile_name,
                    python_key=python_key,
                    python_version=python_version,
                    runner=runner,
                )
            )

    report = ValidationReport(
        schema_version=1,
        bundle_version=bundle.manifest.bundle_version,
        generated_at=_now_timestamp(),
        status=_overall_status(checks),
        checks=checks,
        metadata={"generated_by": "scripts/validate_bundle.py"},
    )
    write_json(
        bundle.root / bundle.manifest.validation_report,
        report.model_dump(exclude_none=True),
    )
    load_bundle_directory(bundle.root)
    return report


def _selected_profiles(
    *,
    available_profiles: Sequence[str],
    requested_profiles: Sequence[str] | None,
) -> list[str]:
    selected_profiles = list(requested_profiles or available_profiles)
    unknown_profiles = sorted(set(selected_profiles).difference(available_profiles))
    if unknown_profiles:
        raise ValueError(f"Unknown bundle profiles: {', '.join(unknown_profiles)}.")
    return selected_profiles


def python_version_from_key(python_key: str) -> str:
    if not python_key.startswith("py") or len(python_key) < 4:
        raise ValueError(f"Invalid Python version key: {python_key!r}.")
    version = python_key[2:]
    return f"{version[0]}.{version[1:]}"


def _selected_python_keys(
    constraints: dict[str, str],
    python_versions: Sequence[str] | None,
) -> list[str]:
    if python_versions is None:
        return sorted(constraints)
    return [f"py{version.replace('.', '')}" for version in python_versions]


def _validate_data_contracts(
    bundle: BundleDirectory,
    profiles: Sequence[str],
    artifact_verifier: ArtifactVerifier,
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
            _verify_source_release_manifest(
                country_id=country_id,
                source_release_manifest_uri=country.metadata.get(
                    "source_release_manifest_uri"
                ),
                expected_sha256=country.metadata.get("source_release_manifest_sha256"),
                artifact_verifier=artifact_verifier,
                failures=failures,
            )
            for artifact_key, artifact in country.datasets.items():
                if artifact.status == "certified" and not artifact.sha256:
                    failures.append(f"{artifact_key} missing sha256")
                    continue
                if artifact.status != "certified":
                    continue
                artifact_uri = _artifact_uri(country, artifact)
                if artifact_uri is None:
                    failures.append(f"{artifact_key} missing artifact URI")
                    continue
                try:
                    verification = artifact_verifier(artifact_uri)
                except Exception as exc:
                    failures.append(f"{artifact_key} could not be read: {exc}")
                    continue
                if verification.sha256 != artifact.sha256:
                    failures.append(
                        f"{artifact_key} sha256 mismatch: expected "
                        f"{artifact.sha256}, got {verification.sha256}"
                    )
                if (
                    artifact.size_bytes is not None
                    and verification.size_bytes != artifact.size_bytes
                ):
                    failures.append(
                        f"{artifact_key} size mismatch: expected "
                        f"{artifact.size_bytes}, got {verification.size_bytes}"
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


def _verify_source_release_manifest(
    *,
    country_id: str,
    source_release_manifest_uri: object,
    expected_sha256: object,
    artifact_verifier: ArtifactVerifier,
    failures: list[str],
) -> None:
    if not isinstance(source_release_manifest_uri, str):
        failures.append(f"{country_id} missing source release manifest URI")
        return
    if not isinstance(expected_sha256, str):
        failures.append(f"{country_id} missing source release manifest sha256")
        return
    try:
        verification = artifact_verifier(source_release_manifest_uri)
    except Exception as exc:
        failures.append(f"{country_id} release manifest could not be read: {exc}")
        return
    if verification.sha256 != expected_sha256:
        failures.append(
            f"{country_id} release manifest sha256 mismatch: expected "
            f"{expected_sha256}, got {verification.sha256}"
        )


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
    python_key: str,
    python_version: str,
    runner: CommandRunner,
) -> list[ValidationCheck]:
    profile = bundle.manifest.profiles[profile_name]
    constraints_path = profile.constraints.get(python_key)
    lockfile_path = profile.lockfiles.get(python_key)
    checks: list[ValidationCheck] = []
    if constraints_path is None:
        return [
            ValidationCheck(
                name="constraints_present",
                status="failed",
                profile=profile_name,
                python_version=python_version,
                details={"missing": python_key},
            )
        ]
    if lockfile_path is None:
        checks.append(
            ValidationCheck(
                name="lockfile_present",
                status="failed",
                profile=profile_name,
                python_version=python_version,
                details={"missing": python_key},
            )
        )
    else:
        checks.append(
            _validate_lockfile(
                bundle=bundle,
                profile_name=profile_name,
                python_version=python_version,
                lockfile_path=lockfile_path,
            )
        )

    constraints_file = bundle.root / constraints_path
    if not constraints_file.exists():
        checks.append(
            ValidationCheck(
                name="constraints_present",
                status="failed",
                profile=profile_name,
                python_version=python_version,
                details={"path": constraints_path},
            )
        )
        return checks
    checks.append(
        ValidationCheck(
            name="constraints_present",
            status="passed",
            profile=profile_name,
            python_version=python_version,
            details={"path": constraints_path},
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
                    python_version,
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
                    _package_version_check_code(bundle, profile.packages),
                ],
            ),
            (
                "import_smoke",
                [
                    str(python),
                    "-c",
                    _import_smoke_code(profile.packages),
                ],
            ),
        ]
        commands.extend(
            (
                f"{country_id}_household_smoke",
                [str(python), "-c", _household_smoke_code(country_id)],
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
                    python_version=python_version,
                    runner=runner,
                )
            )
    return checks


def _validate_lockfile(
    *,
    bundle: BundleDirectory,
    profile_name: str,
    python_version: str,
    lockfile_path: str,
) -> ValidationCheck:
    path = bundle.root / lockfile_path
    if not path.exists():
        return ValidationCheck(
            name="lockfile_present",
            status="failed",
            profile=profile_name,
            python_version=python_version,
            details={"path": lockfile_path, "reason": "lockfile does not exist"},
        )
    try:
        tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        return ValidationCheck(
            name="lockfile_present",
            status="failed",
            profile=profile_name,
            python_version=python_version,
            details={"path": lockfile_path, "reason": str(exc)},
        )
    return ValidationCheck(
        name="lockfile_present",
        status="passed",
        profile=profile_name,
        python_version=python_version,
        details={"path": lockfile_path},
    )


def _run_check(
    *,
    name: str,
    command: list[str],
    profile: str,
    python_version: str,
    runner: CommandRunner,
) -> ValidationCheck:
    started_at = _now_timestamp()
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
            details={"error": str(exc)},
        )
    return ValidationCheck(
        name=name,
        status="passed",
        profile=profile,
        python_version=python_version,
        command=" ".join(command),
        started_at=started_at,
        ended_at=_now_timestamp(),
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
        f"expected = {json.dumps(expected, sort_keys=True)!r}\n"
        "for name, version in expected.items():\n"
        "    actual = md.version(name)\n"
        "    assert actual == version, f'{name}: expected {version}, got {actual}'\n"
    )


def _import_smoke_code(package_names: Sequence[str]) -> str:
    imports = [IMPORT_NAMES[name] for name in package_names if name in IMPORT_NAMES]
    return "\n".join(f"import {module}" for module in imports) + "\n"


def _household_smoke_code(country_id: str) -> str:
    if country_id == "us":
        return (
            "import policyengine as pe\n"
            "pe.us.calculate_household("
            "people=[{'age': 35}], "
            "tax_unit={'filing_status': 'SINGLE'}, "
            "year=2026"
            ")\n"
        )
    if country_id == "uk":
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


def verify_artifact_uri(uri: str) -> ArtifactVerification:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        return _hash_file(path)
    if parsed.scheme == "hf":
        return _hash_url(_hf_download_url(uri))
    raise ValueError(f"Unsupported artifact URI scheme: {uri!r}.")


def _hash_file(path: Path) -> ArtifactVerification:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    return ArtifactVerification(sha256=digest.hexdigest(), size_bytes=size_bytes)


def _hash_url(url: str) -> ArtifactVerification:
    digest = hashlib.sha256()
    size_bytes = 0
    request = urllib.request.Request(url)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token and "huggingface.co" in urllib.parse.urlparse(url).netloc:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=300) as response:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            size_bytes += len(chunk)
    return ArtifactVerification(sha256=digest.hexdigest(), size_bytes=size_bytes)


def _hf_download_url(uri: str) -> str:
    parsed = urllib.parse.urlparse(uri)
    if parsed.netloc in {"model", "dataset", "space"}:
        repo_type = parsed.netloc
        rest = parsed.path.lstrip("/")
    else:
        repo_type = "model"
        rest = f"{parsed.netloc}{parsed.path}"

    repo_id, revision, path = _parse_hf_reference_parts(rest)
    prefix = {
        "model": "",
        "dataset": "datasets/",
        "space": "spaces/",
    }[repo_type]
    quoted_path = "/".join(urllib.parse.quote(part) for part in path.split("/"))
    return (
        f"https://huggingface.co/{prefix}{repo_id}/resolve/"
        f"{urllib.parse.quote(revision)}/{quoted_path}"
    )


def _parse_hf_reference_parts(rest: str) -> tuple[str, str, str]:
    if "@" not in rest:
        raise ValueError(
            "HF URIs must include an immutable revision, for example "
            "hf://model/org/repo@version/path."
        )

    repo_id, revision_and_path = rest.split("@", 1)
    if "/" in revision_and_path:
        revision, path = revision_and_path.split("/", 1)
        if repo_id and revision and path:
            return repo_id, revision, path

    repo_and_path, revision = rest.rsplit("@", 1)
    parts = repo_and_path.split("/")
    if len(parts) < 3:
        raise ValueError("Legacy HF URIs must use hf://org/repo/path@revision form.")
    repo_id = "/".join(parts[:2])
    path = "/".join(parts[2:])
    if not repo_id or not revision or not path:
        raise ValueError(f"Incomplete HF URI reference: {rest!r}.")
    return repo_id, revision, path
