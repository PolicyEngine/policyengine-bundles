from __future__ import annotations

import hashlib
import importlib
import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from policyengine_bundles.http import request_with_retries
from policyengine_bundles.io import JsonDict, load_json, write_bytes, write_json
from policyengine_bundles.models import (
    ArtifactRelease,
    BundleCandidate,
    BundleManifest,
    CandidateCountry,
    CertificationEvidence,
    CountryBundle,
    CountryCertification,
    DataArtifact,
    DataBuildInfo,
    DataPackageReference,
    DataReleaseManifest,
    PackagePin,
    Profile,
    RuntimeComponentMetadata,
    ValidationCheck,
    ValidationReport,
)
from policyengine_bundles.references import HuggingFaceReference, hugging_face_token
from policyengine_bundles.validation import load_bundle_directory

PackageResolver = Callable[[str, str], PackagePin]
ManifestLoader = Callable[[str], "LoadedManifest"]
ComponentMetadataResolver = Callable[[PackagePin], RuntimeComponentMetadata | None]


PACKAGE_IMPORT_NAMES = {
    "policyengine-core": "policyengine_core",
    "policyengine-us": "policyengine_us",
    "policyengine-uk": "policyengine_uk",
}


@dataclass(frozen=True)
class LoadedManifest:
    payload: JsonDict
    uri: str
    sha256: str
    content: bytes
    local_path: Path | None = None
    repo_id: str | None = None
    repo_type: str | None = None
    revision: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class _RuntimeCertification:
    basis: str
    certified_by: str
    runtime_model_package: RuntimeComponentMetadata | None = None
    runtime_core_package: RuntimeComponentMetadata | PackagePin | None = None
    evidence: list[CertificationEvidence] | None = None
    metadata: dict[str, Any] | None = None


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _now_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_pypi_package(name: str, version: str) -> PackagePin:
    with urllib.request.urlopen(
        f"https://pypi.org/pypi/{urllib.parse.quote(name)}/{version}/json",
        timeout=30,
    ) as response:
        payload = json.load(response)

    urls = payload.get("urls", [])
    wheel = next(
        (item for item in urls if item.get("packagetype") == "bdist_wheel"),
        None,
    )
    sdist = next((item for item in urls if item.get("packagetype") == "sdist"), None)
    if wheel is None:
        raise ValueError(f"No wheel found on PyPI for {name}=={version}.")

    return PackagePin(
        name=payload["info"]["name"],
        version=payload["info"]["version"],
        resolution_status="pinned",
        wheel_url=wheel.get("url"),
        sdist_url=sdist.get("url") if sdist else None,
        sha256=wheel.get("digests", {}).get("sha256"),
        source="pypi",
    )


def resolve_component_metadata(
    package: PackagePin,
) -> RuntimeComponentMetadata | None:
    """Load dependency-light runtime metadata from an installed component package."""
    if package.version is None:
        return None
    import_name = PACKAGE_IMPORT_NAMES.get(package.name, package.name.replace("-", "_"))
    for module_name in (f"{import_name}.build_metadata", import_name):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        get_runtime_metadata = getattr(module, "get_runtime_metadata", None)
        if get_runtime_metadata is None:
            continue
        metadata = RuntimeComponentMetadata.model_validate(get_runtime_metadata())
        if metadata.name == package.name and metadata.version == package.version:
            return metadata
    return None


def load_release_manifest_uri(uri: str) -> LoadedManifest:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        content = path.read_bytes()
        return LoadedManifest(
            payload=json.loads(content),
            uri=uri,
            sha256=_sha256_bytes(content),
            content=content,
            local_path=path,
        )
    if parsed.scheme == "hf":
        hf_ref = HuggingFaceReference.parse(uri)
        content = _read_hf_bytes(hf_ref)
        return LoadedManifest(
            payload=json.loads(content),
            uri=hf_ref.to_uri(),
            sha256=_sha256_bytes(content),
            content=content,
            repo_id=hf_ref.repo_id,
            repo_type=hf_ref.repo_type,
            revision=hf_ref.revision,
            path=hf_ref.path,
        )
    raise ValueError(f"Unsupported release manifest URI scheme: {uri!r}.")


def _read_hf_bytes(reference: HuggingFaceReference) -> bytes:
    def read_once() -> bytes:
        request = urllib.request.Request(reference.download_url())
        token = hugging_face_token()
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    return request_with_retries(read_once)


def generate_bundle(
    candidate_path: Path | str,
    output_dir: Path | str,
    *,
    package_resolver: PackageResolver = resolve_pypi_package,
    manifest_loader: ManifestLoader = load_release_manifest_uri,
    component_metadata_resolver: ComponentMetadataResolver = resolve_component_metadata,
    force: bool = False,
    testing_only: bool = False,
    embed_local_manifests: bool = False,
) -> None:
    candidate = BundleCandidate.model_validate(load_json(Path(candidate_path)))
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()) and not force:
        raise ValueError(
            f"Output directory already exists and is not empty: {output_root}"
        )

    created_at = _now_timestamp()
    package_pins = _resolve_package_pins(candidate, package_resolver)
    countries: dict[str, CountryBundle] = {}
    embedded_manifest_payloads: dict[Path, bytes] = {}
    for country_id, candidate_country in candidate.countries.items():
        loaded_manifest = manifest_loader(candidate_country.data_release_manifest_uri)
        local_manifest_path = _local_release_manifest_output_path(
            country_id=country_id,
            loaded_manifest=loaded_manifest,
            testing_only=testing_only,
            embed_local_manifests=embed_local_manifests,
        )
        if local_manifest_path is not None:
            embedded_manifest_payloads[local_manifest_path] = loaded_manifest.content
        countries[country_id] = _build_country_bundle(
            bundle_version=candidate.bundle_version,
            country_id=country_id,
            country=candidate_country,
            packages=package_pins,
            loaded_manifest=loaded_manifest,
            release_manifest_path=(
                local_manifest_path.as_posix()
                if local_manifest_path is not None
                else None
            ),
            component_metadata_resolver=component_metadata_resolver,
        )
    _validate_core_agreement(package_pins, countries)

    validation_report = ValidationReport(
        schema_version=1,
        bundle_version=candidate.bundle_version,
        generated_at=created_at,
        status="skipped",
        checks=[
            ValidationCheck(
                name="bundle_runtime_validation",
                status="skipped",
                details={
                    "reason": (
                        "Runtime validation is performed by scripts/validate_bundle.py."
                    )
                },
            )
        ],
        metadata={"generated_by": "scripts/generate_bundle.py"},
    )
    manifest = BundleManifest(
        schema_version=1,
        bundle_version=candidate.bundle_version,
        policyengine=package_pins["policyengine"],
        packages=package_pins,
        profiles=_build_profiles(candidate),
        countries={
            country_id: f"countries/{country_id}.json"
            for country_id in sorted(countries)
        },
        validation_report="validation-report.json",
        created_at=created_at,
        metadata={
            "python_versions": candidate.python_versions,
            "generated_by": "scripts/generate_bundle.py",
            "testing_only": testing_only,
        },
    )

    write_json(output_root / "bundle.json", manifest.model_dump(exclude_none=True))
    for relative_path, content in embedded_manifest_payloads.items():
        write_bytes(output_root / relative_path, content)
    for country_id, country_bundle in countries.items():
        write_json(
            output_root / "countries" / f"{country_id}.json",
            country_bundle.model_dump(exclude_none=True),
        )
    write_json(
        output_root / "validation-report.json",
        validation_report.model_dump(exclude_none=True),
    )
    load_bundle_directory(output_root)


def _resolve_package_pins(
    candidate: BundleCandidate,
    package_resolver: PackageResolver,
) -> dict[str, PackagePin]:
    pins = {
        "policyengine": PackagePin(
            name="policyengine",
            version=candidate.policyengine_version,
            resolution_status="pinned",
            role="bundle_carrier",
        )
    }
    pins.update(
        {
            name: _require_exact_pin(package_resolver(name, version))
            for name, version in candidate.packages.items()
        }
    )
    return pins


def _require_exact_pin(pin: PackagePin) -> PackagePin:
    if pin.version is None:
        raise ValueError(f"{pin.name} must resolve to an exact version.")
    if pin.resolution_status not in {None, "pinned"}:
        raise ValueError(f"{pin.name} must be pinned, got {pin.resolution_status}.")
    if pin.sha256 is None:
        raise ValueError(f"{pin.name} must include a wheel sha256.")
    return pin.model_copy(update={"resolution_status": "pinned"})


def _build_country_bundle(
    *,
    bundle_version: str,
    country_id: str,
    country: CandidateCountry,
    packages: Mapping[str, PackagePin],
    loaded_manifest: LoadedManifest,
    release_manifest_path: str | None,
    component_metadata_resolver: ComponentMetadataResolver,
) -> CountryBundle:
    release = DataReleaseManifest.model_validate(loaded_manifest.payload)
    release = _rewrite_artifacts_to_loaded_revision(release, loaded_manifest)
    model_package = packages[country.model_package]
    core_package = packages["policyengine-core"]
    build = _require_build_metadata(release)
    built_with_model_package = _require_exact_build_package(
        release=release,
        package=build.built_with_model_package,
        field_name="built_with_model_package",
    )
    built_with_core_package = _require_exact_build_package(
        release=release,
        package=build.built_with_core_package,
        field_name="built_with_core_package",
    )
    runtime_certification = _certify_runtime_compatibility(
        release=release,
        country=country,
        model_package=model_package,
        core_package=core_package,
        built_with_model_package=built_with_model_package,
        built_with_core_package=built_with_core_package,
        component_metadata_resolver=component_metadata_resolver,
    )

    default_dataset = _default_dataset(release)
    artifact_release = _artifact_release(
        release=release,
        loaded_manifest=loaded_manifest,
        release_manifest_uri=(
            None
            if loaded_manifest.local_path is not None and release_manifest_path
            else loaded_manifest.uri
        ),
    )
    data_package = DataPackageReference(
        name=release.data_package.name,
        version=release.data_package.version,
        repo_id=artifact_release.repo_id,
        repo_type=artifact_release.repo_type,
        release_manifest_path=release_manifest_path
        or _release_manifest_path(loaded_manifest),
    )
    return CountryBundle(
        schema_version=1,
        bundle_version=bundle_version,
        country_id=country_id,
        model_package=model_package,
        core_package=core_package,
        data_package=data_package,
        artifact_release=artifact_release,
        default_dataset=default_dataset,
        datasets=release.artifacts,
        certification=CountryCertification(
            compatibility_basis=runtime_certification.basis,
            built_with_model_package=_metadata_to_package_pin(
                built_with_model_package,
            ),
            built_with_core_package=_metadata_to_package_pin(
                built_with_core_package,
            ),
            certified_for_model_package=model_package,
            certified_for_core_package=core_package,
            certified_by=runtime_certification.certified_by,
            data_build_id=build.build_id,
            data_build_fingerprint=(
                built_with_model_package.data_build_fingerprint
                if hasattr(built_with_model_package, "data_build_fingerprint")
                else None
            ),
            runtime_model_package=runtime_certification.runtime_model_package,
            runtime_core_package=runtime_certification.runtime_core_package,
            evidence=runtime_certification.evidence or [],
            metadata=runtime_certification.metadata or {},
        ),
        metadata={
            "input_release_manifest_uri": loaded_manifest.uri,
            "input_release_manifest_sha256": loaded_manifest.sha256,
        },
    )


def _require_build_metadata(release: DataReleaseManifest) -> DataBuildInfo:
    if release.build is None:
        raise ValueError(
            f"{release.data_package.name}=={release.data_package.version} must "
            "record build metadata for bundle certification."
        )
    return release.build


def _require_exact_build_package(
    *,
    release: DataReleaseManifest,
    package: RuntimeComponentMetadata | PackagePin | None,
    field_name: str,
) -> RuntimeComponentMetadata | PackagePin:
    if package is None:
        raise ValueError(
            f"{release.data_package.name}=={release.data_package.version} must "
            f"record {field_name} for bundle certification."
        )
    if package.version is None:
        raise ValueError(
            f"{release.data_package.name}=={release.data_package.version} "
            f"{field_name} must record an exact version."
        )
    return package


def _certify_runtime_compatibility(
    *,
    release: DataReleaseManifest,
    country: CandidateCountry,
    model_package: PackagePin,
    core_package: PackagePin,
    built_with_model_package: RuntimeComponentMetadata | PackagePin,
    built_with_core_package: RuntimeComponentMetadata | PackagePin,
    component_metadata_resolver: ComponentMetadataResolver,
) -> _RuntimeCertification:
    if _package_metadata_matches_pin(
        built_with_model_package,
        model_package,
    ) and _package_metadata_matches_pin(built_with_core_package, core_package):
        return _RuntimeCertification(
            basis="data_release_build_package_match",
            certified_by="policyengine-bundles generator",
        )

    runtime_model_package = component_metadata_resolver(model_package)
    runtime_core_package = component_metadata_resolver(core_package)
    if (
        _package_metadata_matches_pin(built_with_core_package, core_package)
        and built_with_model_package.name == model_package.name
        and runtime_model_package is not None
        and _package_metadata_matches_pin(runtime_model_package, model_package)
        and (
            runtime_core_package is None
            or _package_metadata_matches_pin(runtime_core_package, core_package)
        )
        and runtime_model_package.data_build_fingerprint is not None
        and hasattr(built_with_model_package, "data_build_fingerprint")
        and runtime_model_package.data_build_fingerprint
        == built_with_model_package.data_build_fingerprint
    ):
        return _RuntimeCertification(
            basis="matching_data_build_fingerprint",
            certified_by="policyengine-bundles generator",
            runtime_model_package=runtime_model_package,
            runtime_core_package=runtime_core_package,
        )

    if country.certification is not None:
        return _RuntimeCertification(
            basis=country.certification.basis,
            certified_by=country.certification.certified_by,
            runtime_model_package=runtime_model_package,
            runtime_core_package=runtime_core_package,
            evidence=country.certification.evidence,
            metadata={
                **country.certification.metadata,
                "reason": country.certification.reason,
            },
        )

    raise ValueError(
        f"{release.data_package.name}=={release.data_package.version} is not "
        f"certified for {model_package.name}=={model_package.version} and "
        f"{core_package.name}=={core_package.version}. Add matching runtime "
        "metadata or an explicit candidate certification."
    )


def _package_metadata_matches_pin(
    metadata: RuntimeComponentMetadata | PackagePin,
    package: PackagePin,
) -> bool:
    return metadata.name == package.name and metadata.version == package.version


def _local_release_manifest_output_path(
    *,
    country_id: str,
    loaded_manifest: LoadedManifest,
    testing_only: bool,
    embed_local_manifests: bool,
) -> Path | None:
    if loaded_manifest.local_path is None:
        return None
    if embed_local_manifests:
        return Path("source-manifests") / country_id / "release_manifest.json"
    if testing_only:
        return None
    raise ValueError(
        "Local file release manifests are only allowed with testing_only=True "
        "or embed_local_manifests=True. Certified bundles should use immutable "
        "remote release manifest URIs."
    )


def _release_manifest_path(loaded_manifest: LoadedManifest) -> str:
    if loaded_manifest.repo_id and loaded_manifest.path:
        return loaded_manifest.path
    return "release_manifest.json"


def _default_dataset(release: DataReleaseManifest) -> str:
    if not release.default_datasets:
        raise ValueError(
            f"{release.data_package.name}=={release.data_package.version} has no "
            "default_datasets entries."
        )
    if "national" in release.default_datasets:
        return release.default_datasets["national"]
    return next(iter(release.default_datasets.values()))


def _artifact_release(
    *,
    release: DataReleaseManifest,
    loaded_manifest: LoadedManifest,
    release_manifest_uri: str | None,
) -> ArtifactRelease:
    metadata_release = release.metadata.get("artifact_release", {})
    repo_id = (
        metadata_release.get("repo_id")
        or loaded_manifest.repo_id
        or _first_artifact_repo_id(release.artifacts)
    )
    if repo_id is None:
        raise ValueError(
            f"{release.data_package.name}=={release.data_package.version} does not "
            "record an artifact repo_id."
        )
    return ArtifactRelease(
        repo_id=repo_id,
        repo_type=metadata_release.get("repo_type")
        or loaded_manifest.repo_type
        or "model",
        version=loaded_manifest.revision
        or metadata_release.get("version")
        or release.data_package.version,
        release_manifest_uri=release_manifest_uri,
        release_manifest_sha256=loaded_manifest.sha256,
    )


def _rewrite_artifacts_to_loaded_revision(
    release: DataReleaseManifest,
    loaded_manifest: LoadedManifest,
) -> DataReleaseManifest:
    if not loaded_manifest.repo_id or not loaded_manifest.revision:
        return release

    metadata_release = release.metadata.get("artifact_release", {})
    replaceable_revisions = {
        value
        for value in (
            release.data_package.version,
            metadata_release.get("version"),
            loaded_manifest.revision,
        )
        if value
    }
    artifacts = {
        key: _rewrite_artifact_to_revision(
            artifact,
            repo_id=loaded_manifest.repo_id,
            revision=loaded_manifest.revision,
            replaceable_revisions=replaceable_revisions,
        )
        for key, artifact in release.artifacts.items()
    }
    if artifacts == release.artifacts:
        return release
    return release.model_copy(update={"artifacts": artifacts})


def _rewrite_artifact_to_revision(
    artifact: DataArtifact,
    *,
    repo_id: str,
    revision: str,
    replaceable_revisions: set[str],
) -> DataArtifact:
    parsed_uri = _parse_artifact_uri(artifact.uri)
    artifact_repo_id = artifact.repo_id or (parsed_uri.repo_id if parsed_uri else None)
    artifact_revision = artifact.revision or (
        parsed_uri.revision if parsed_uri else None
    )
    if artifact_repo_id != repo_id or artifact_revision not in replaceable_revisions:
        return artifact

    updates: dict[str, str] = {}
    if artifact.revision is not None:
        updates["revision"] = revision
    if (
        parsed_uri is not None
        and parsed_uri.repo_id == repo_id
        and parsed_uri.revision in replaceable_revisions
    ):
        updates["uri"] = HuggingFaceReference(
            repo_type=parsed_uri.repo_type,
            repo_id=parsed_uri.repo_id,
            revision=revision,
            path=parsed_uri.path,
        ).to_uri()
    if not updates:
        return artifact
    return artifact.model_copy(update=updates)


def _parse_artifact_uri(uri: str | None) -> HuggingFaceReference | None:
    if uri is None:
        return None
    try:
        return HuggingFaceReference.parse(uri)
    except ValueError:
        return None


def _first_artifact_repo_id(artifacts: Mapping[str, DataArtifact]) -> str | None:
    for artifact in artifacts.values():
        if artifact.repo_id:
            return artifact.repo_id
    return None


def _metadata_to_package_pin(
    metadata: RuntimeComponentMetadata | PackagePin,
) -> PackagePin:
    if isinstance(metadata, PackagePin):
        return metadata
    return PackagePin(
        name=metadata.name,
        version=metadata.version,
        resolution_status="pinned",
        git_sha=metadata.git_sha,
        wheel_url=metadata.wheel_url,
        sha256=metadata.wheel_sha256,
    )


def _validate_core_agreement(
    packages: Mapping[str, PackagePin],
    countries: Mapping[str, CountryBundle],
) -> None:
    core_version = packages["policyengine-core"].version
    mismatches = [
        country_id
        for country_id, country in countries.items()
        if country.core_package.version != core_version
        or country.certification.certified_for_core_package.version != core_version
    ]
    if mismatches:
        raise ValueError(
            "All countries must certify the same exact policyengine-core version; "
            f"mismatched countries: {', '.join(sorted(mismatches))}."
        )


def _build_profiles(candidate: BundleCandidate) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    for profile in candidate.profiles:
        if profile == "all":
            country_ids = sorted(candidate.countries)
        else:
            country_ids = [profile]
        package_names = ["policyengine", "policyengine-core"]
        for country_id in country_ids:
            model_package = candidate.countries[country_id].model_package
            if model_package not in package_names:
                package_names.append(model_package)
        profiles[profile] = Profile(
            description=f"{profile} runtime profile generated from bundle candidate.",
            packages=package_names,
            countries=country_ids,
        )
    return profiles
