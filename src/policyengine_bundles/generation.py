from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from policyengine_bundles.http import request_with_retries
from policyengine_bundles.io import JsonDict, load_json, write_bytes, write_json
from policyengine_bundles.models import (
    ArtifactRelease,
    BundleCandidate,
    BundleManifest,
    CandidateCountry,
    CompatibilityAssertion,
    CountryBundle,
    DataArtifact,
    DataPackageReference,
    DataReleaseManifest,
    PackagePin,
    ValidationCheck,
    ValidationReport,
)
from policyengine_bundles.references import HuggingFaceReference, hugging_face_token
from policyengine_bundles.validation import load_bundle_directory

PackageResolver = Callable[[str, str], PackagePin]
ManifestLoader = Callable[[str], "LoadedManifest"]


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
        )

    validation_report = ValidationReport(
        schema_version=2,
        bundle_version=candidate.bundle_version,
        generated_at=created_at,
        status="skipped",
        checks=[
            ValidationCheck(
                name="registry_validation",
                status="skipped",
                details={"reason": "Run scripts/validate_bundle.py before release."},
            )
        ],
        metadata={
            "generated_by": "scripts/generate_bundle.py",
            "validation_kind": "registry",
        },
    )
    manifest = BundleManifest(
        schema_version=2,
        bundle_version=candidate.bundle_version,
        policyengine=package_pins["policyengine"],
        packages=package_pins,
        countries={
            country_id: f"countries/{country_id}.json"
            for country_id in sorted(countries)
        },
        validation_report="validation-report.json",
        created_at=created_at,
        metadata={
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
            version=candidate.bundle_version,
            resolution_status="pinned",
            role="bundle_carrier",
        )
    }
    pins.update(
        {
            name: _require_exact_pin(package_resolver(name, version))
            for name, version in sorted(candidate.packages.items())
        }
    )
    return pins


def _require_exact_pin(pin: PackagePin) -> PackagePin:
    if not pin.version:
        raise ValueError(f"{pin.name} must resolve to an exact version.")
    if pin.resolution_status != "pinned":
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
) -> CountryBundle:
    release = DataReleaseManifest.model_validate(loaded_manifest.payload)
    release = _rewrite_artifacts_to_loaded_revision(release, loaded_manifest)
    return _assemble_country_bundle(
        release=release,
        loaded_manifest=loaded_manifest,
        country=country,
        country_id=country_id,
        bundle_version=bundle_version,
        packages=packages,
        release_manifest_path=release_manifest_path,
    )


def _build_provenance_metadata(release: DataReleaseManifest) -> dict[str, str]:
    """Build provenance keys consumed by downstream bundle importers."""
    build = release.build
    if build is None:
        return {}
    metadata: dict[str, str] = {}
    if build.build_id:
        metadata["data_build_id"] = build.build_id
    model_build = build.built_with_model_package
    if model_build is not None:
        metadata["built_with_model_version"] = model_build.version
        if model_build.git_sha:
            metadata["built_with_model_git_sha"] = model_build.git_sha
        if model_build.data_build_fingerprint:
            metadata["data_build_fingerprint"] = model_build.data_build_fingerprint
    return metadata


def _assemble_country_bundle(
    *,
    release: DataReleaseManifest,
    loaded_manifest: LoadedManifest,
    country: CandidateCountry,
    country_id: str,
    bundle_version: str,
    packages: Mapping[str, PackagePin],
    release_manifest_path: str | None,
) -> CountryBundle:
    model_package = packages[country.model_package]
    core_package = packages["policyengine-core"]
    default_dataset = _default_dataset(release)
    artifact_release = _artifact_release(
        release=release,
        loaded_manifest=loaded_manifest,
        release_manifest_uri=loaded_manifest.uri,
    )
    data_package = DataPackageReference(
        name=release.data_package.name,
        version=release.data_package.version,
        repo_id=artifact_release.repo_id,
        repo_type=artifact_release.repo_type,
        release_manifest_path=release_manifest_path
        or _release_manifest_path(loaded_manifest),
        release_manifest_revision=loaded_manifest.revision,
    )
    return CountryBundle(
        schema_version=2,
        bundle_version=bundle_version,
        country_id=country_id,
        model_package=model_package,
        core_package=core_package,
        data_package=data_package,
        artifact_release=artifact_release,
        default_dataset=default_dataset,
        datasets=release.artifacts,
        region_datasets=_region_datasets(release),
        compatibility=CompatibilityAssertion(
            model_package=model_package,
            core_package=core_package,
            data_package=release.data_package,
            release_manifest_uri=loaded_manifest.uri,
            release_manifest_sha256=loaded_manifest.sha256,
            metadata={
                "candidate_model_package": country.model_package,
                "candidate_data_release_manifest_uri": (
                    country.data_release_manifest_uri
                ),
                **_build_provenance_metadata(release),
            },
        ),
        metadata={
            "input_release_manifest_uri": loaded_manifest.uri,
            "input_release_manifest_sha256": loaded_manifest.sha256,
        },
    )


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
        "or embed_local_manifests=True. Published bundles should use immutable "
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


def _region_datasets(release: DataReleaseManifest) -> dict:
    raw_region_datasets = release.metadata.get("region_datasets")
    if isinstance(raw_region_datasets, dict):
        return raw_region_datasets
    return {}


def _artifact_release(
    *,
    release: DataReleaseManifest,
    loaded_manifest: LoadedManifest,
    release_manifest_uri: str,
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
