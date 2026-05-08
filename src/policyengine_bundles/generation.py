from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from policyengine_bundles.models import (
    ArtifactRelease,
    BundleManifest,
    BundleModel,
    CountryBundle,
    CountryCertification,
    DataArtifact,
    DataPackageReference,
    DataReleaseManifest,
    PackagePin,
    Profile,
    ValidationCheck,
    ValidationReport,
)
from policyengine_bundles.validation import load_bundle_directory

JsonDict = dict[str, Any]
PackageResolver = Callable[[str, str], PackagePin]
ManifestLoader = Callable[[str], "LoadedManifest"]


class CandidateCountry(BundleModel):
    model_package: str
    data_release_manifest_uri: str


class BundleCandidate(BundleModel):
    schema_version: Literal[1]
    bundle_version: str
    policyengine_version: str
    python_versions: list[str] = Field(default_factory=list)
    profiles: list[str]
    packages: dict[str, str]
    countries: dict[str, CandidateCountry]

    @model_validator(mode="after")
    def validate_candidate(self) -> BundleCandidate:
        if self.policyengine_version != self.bundle_version:
            raise ValueError(
                "Candidate policyengine_version must match bundle_version. "
                "The bundle version is the human-facing policyengine version."
            )
        if "policyengine-core" not in self.packages:
            raise ValueError("Candidate packages must include policyengine-core.")
        if not self.countries:
            raise ValueError("Candidate must include at least one country.")
        if not self.profiles:
            raise ValueError("Candidate must include at least one profile.")
        for country_id, country in self.countries.items():
            if country.model_package not in self.packages:
                raise ValueError(
                    f"Country {country_id!r} references unknown model package "
                    f"{country.model_package!r}."
                )
        for profile in self.profiles:
            if profile != "all" and profile not in self.countries:
                raise ValueError(
                    f"Profile {profile!r} must be 'all' or a candidate country id."
                )
        return self


@dataclass(frozen=True)
class LoadedManifest:
    payload: JsonDict
    uri: str
    sha256: str
    repo_id: str | None = None
    repo_type: str | None = None
    revision: str | None = None
    path: str | None = None


def load_json(path: Path) -> JsonDict:
    with path.open() as file:
        return json.load(file)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


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
            path=str(path),
        )
    if parsed.scheme == "hf":
        hf_ref = parse_hf_uri(uri)
        content = _read_hf_bytes(hf_ref)
        return LoadedManifest(
            payload=json.loads(content),
            uri=uri,
            sha256=_sha256_bytes(content),
            repo_id=hf_ref.repo_id,
            repo_type=hf_ref.repo_type,
            revision=hf_ref.revision,
            path=hf_ref.path,
        )
    raise ValueError(f"Unsupported release manifest URI scheme: {uri!r}.")


@dataclass(frozen=True)
class HuggingFaceReference:
    repo_type: str
    repo_id: str
    revision: str
    path: str


def parse_hf_uri(uri: str) -> HuggingFaceReference:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "hf":
        raise ValueError(f"Expected hf:// URI, got {uri!r}.")

    if parsed.netloc in {"model", "dataset", "space"}:
        repo_type = parsed.netloc
        rest = parsed.path.lstrip("/")
    else:
        repo_type = "model"
        rest = f"{parsed.netloc}{parsed.path}"

    try:
        repo_id, revision_and_path = rest.split("@", 1)
        revision, path = revision_and_path.split("/", 1)
    except ValueError as exc:
        raise ValueError(
            "HF URIs must be hf://<repo_id>@<revision>/<path> or "
            "hf://<repo_type>/<repo_id>@<revision>/<path>."
        ) from exc
    if not repo_id or not revision or not path:
        raise ValueError(f"Incomplete HF URI: {uri!r}.")
    return HuggingFaceReference(
        repo_type=repo_type,
        repo_id=repo_id,
        revision=revision,
        path=path,
    )


def _read_hf_bytes(reference: HuggingFaceReference) -> bytes:
    prefix = {
        "model": "",
        "dataset": "datasets/",
        "space": "spaces/",
    }[reference.repo_type]
    quoted_path = "/".join(
        urllib.parse.quote(part) for part in reference.path.split("/")
    )
    url = (
        f"https://huggingface.co/{prefix}{reference.repo_id}/resolve/"
        f"{urllib.parse.quote(reference.revision)}/{quoted_path}"
    )
    request = urllib.request.Request(url)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def generate_bundle(
    candidate_path: Path | str,
    output_dir: Path | str,
    *,
    package_resolver: PackageResolver = resolve_pypi_package,
    manifest_loader: ManifestLoader = load_release_manifest_uri,
    force: bool = False,
) -> None:
    candidate = BundleCandidate.model_validate(load_json(Path(candidate_path)))
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()) and not force:
        raise ValueError(
            f"Output directory already exists and is not empty: {output_root}"
        )

    created_at = _now_timestamp()
    package_pins = _resolve_package_pins(candidate, package_resolver)
    countries = {
        country_id: _build_country_bundle(
            bundle_version=candidate.bundle_version,
            country_id=country_id,
            country=candidate_country,
            packages=package_pins,
            loaded_manifest=manifest_loader(
                candidate_country.data_release_manifest_uri
            ),
        )
        for country_id, candidate_country in candidate.countries.items()
    }
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
            "testing_only": True,
        },
    )

    write_json(output_root / "bundle.json", manifest.model_dump(exclude_none=True))
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
    versions = {"policyengine": candidate.policyengine_version, **candidate.packages}
    return {
        name: _require_exact_pin(package_resolver(name, version))
        for name, version in versions.items()
    }


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
) -> CountryBundle:
    release = DataReleaseManifest.model_validate(loaded_manifest.payload)
    model_package = packages[country.model_package]
    core_package = packages["policyengine-core"]
    _validate_release_supports_package(
        release=release,
        package_name=model_package.name,
        version=model_package.version or "",
        compatible_packages=release.compatible_model_packages,
        build_metadata=release.build.built_with_model_package
        if release.build
        else None,
    )
    _validate_release_supports_package(
        release=release,
        package_name=core_package.name,
        version=core_package.version or "",
        compatible_packages=release.compatible_core_packages,
        build_metadata=release.build.built_with_core_package if release.build else None,
    )

    default_dataset = _default_dataset(release)
    artifact_release = _artifact_release(release, loaded_manifest)
    data_package = DataPackageReference(
        name=release.data_package.name,
        version=release.data_package.version,
        repo_id=artifact_release.repo_id,
        repo_type=artifact_release.repo_type,
        release_manifest_path=loaded_manifest.path or "release_manifest.json",
    )
    build = release.build
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
            compatibility_basis="release_manifest_exact_compatibility",
            built_with_model_package=_metadata_to_package_pin(
                build.built_with_model_package if build else None,
                fallback=model_package,
            ),
            built_with_core_package=_metadata_to_package_pin(
                build.built_with_core_package if build else None,
                fallback=core_package,
            ),
            certified_for_model_package=model_package,
            certified_for_core_package=core_package,
            certified_by="policyengine-bundles generator",
            data_build_id=build.build_id if build else None,
            data_build_fingerprint=(
                build.built_with_model_package.data_build_fingerprint
                if build and build.built_with_model_package
                else None
            ),
        ),
        metadata={
            "source_release_manifest_uri": loaded_manifest.uri,
            "source_release_manifest_sha256": loaded_manifest.sha256,
        },
    )


def _validate_release_supports_package(
    *,
    release: DataReleaseManifest,
    package_name: str,
    version: str,
    compatible_packages: list[Any],
    build_metadata: Any,
) -> None:
    if build_metadata is not None and build_metadata.name == package_name:
        if build_metadata.version == version:
            return
    for specifier in compatible_packages:
        if (
            specifier.name == package_name
            and specifier.specifier.strip() == f"=={version}"
        ):
            return
    raise ValueError(
        f"{release.data_package.name}=={release.data_package.version} does not "
        f"declare exact compatibility with {package_name}=={version}."
    )


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
    release: DataReleaseManifest,
    loaded_manifest: LoadedManifest,
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
        version=metadata_release.get("version")
        or loaded_manifest.revision
        or release.data_package.version,
        release_manifest_uri=loaded_manifest.uri,
        release_manifest_sha256=loaded_manifest.sha256,
    )


def _first_artifact_repo_id(artifacts: Mapping[str, DataArtifact]) -> str | None:
    for artifact in artifacts.values():
        if artifact.repo_id:
            return artifact.repo_id
    return None


def _metadata_to_package_pin(metadata: Any, *, fallback: PackagePin) -> PackagePin:
    if metadata is None:
        return fallback
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
