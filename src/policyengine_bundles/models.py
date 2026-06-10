from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BundleModel(BaseModel):
    """Base model for strict bundle metadata contracts."""

    model_config = ConfigDict(extra="forbid")


def _validate_relative_posix_path(path: str, field_name: str) -> None:
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or path in {"", "."}:
        raise ValueError(f"{field_name} must be a bundle-relative POSIX path.")


_VERSION_SPECIFIER_PATTERN = re.compile(r"[<>=!~*,\s]")


def _validate_exact_version(version: str, field_name: str) -> None:
    if not version:
        raise ValueError(f"{field_name} must be a non-empty exact version.")
    if _VERSION_SPECIFIER_PATTERN.search(version):
        raise ValueError(
            f"{field_name} must be an exact version string, not a specifier."
        )


class PackageIdentity(BundleModel):
    name: str
    version: str


class PackagePin(BundleModel):
    name: str
    version: str
    resolution_status: Literal["pinned"] = "pinned"
    role: Literal["runtime_dependency", "bundle_carrier"] | None = None
    wheel_url: str | None = None
    sdist_url: str | None = None
    sha256: str | None = None
    git_sha: str | None = None
    source: str | None = None

    @property
    def is_bundle_carrier(self) -> bool:
        return self.role == "bundle_carrier"


class RuntimeComponentMetadata(BundleModel):
    """Dependency-free metadata emitted by component packages."""

    name: str
    version: str
    git_sha: str | None = None
    wheel_sha256: str | None = None
    wheel_url: str | None = None
    source_path: str | None = None
    data_build_fingerprint: str | None = None
    core: PackagePin | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataPackageReference(BundleModel):
    name: str
    version: str
    repo_id: str
    repo_type: str = "model"
    release_manifest_path: str = "release_manifest.json"
    release_manifest_revision: str | None = None

    @model_validator(mode="after")
    def validate_release_manifest_path(self) -> DataPackageReference:
        _validate_relative_posix_path(
            self.release_manifest_path,
            "release_manifest_path",
        )
        return self


class ArtifactRelease(BundleModel):
    repo_id: str
    version: str
    repo_type: str = "model"
    release_manifest_uri: str
    release_manifest_sha256: str


class PreservationMirror(BundleModel):
    kind: str
    url: str
    doi: str | None = None
    sha256: str | None = None
    deposited_at: str | None = None


class CertificationEvidence(BundleModel):
    kind: str
    subject: str | None = None
    subject_sha256: str | None = None
    uri: str | None = None
    signer: str | None = None
    signature: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactCertification(BundleModel):
    certified_by: str
    certified_at: str | None = None
    scopes: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence: list[CertificationEvidence] = Field(default_factory=list)


class DataArtifact(BundleModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["uri"],
                    "properties": {"uri": {"type": "string"}},
                },
                {
                    "required": ["path", "repo_id", "revision"],
                    "properties": {
                        "path": {"type": "string"},
                        "repo_id": {"type": "string"},
                        "revision": {"type": "string"},
                    },
                },
            ],
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "status": {
                                "enum": [
                                    "certified",
                                    "partially_certified",
                                    "hash_pinned",
                                ],
                            }
                        },
                        "required": ["status"],
                    },
                    "then": {
                        "required": ["sha256"],
                        "properties": {"sha256": {"type": "string"}},
                    },
                },
                {
                    "if": {
                        "properties": {
                            "status": {
                                "enum": ["unverified", "unavailable"],
                            }
                        },
                        "required": ["status"],
                    },
                    "then": {
                        "required": ["missing_reason"],
                        "properties": {"missing_reason": {"type": "string"}},
                    },
                },
                {
                    "if": {
                        "properties": {"status": {"const": "partially_certified"}},
                        "required": ["status"],
                    },
                    "then": {
                        "required": ["certification"],
                        "properties": {
                            "certification": {
                                "required": ["scopes", "limitations"],
                            }
                        },
                    },
                },
            ],
        },
    )

    kind: str
    uri: str | None = None
    path: str | None = None
    repo_id: str | None = None
    revision: str | None = None
    status: Literal[
        "certified",
        "partially_certified",
        "hash_pinned",
        "unverified",
        "unavailable",
    ] = "certified"
    sha256: str | None = None
    metadata_sha256: str | None = None
    missing_reason: str | None = None
    size_bytes: int | None = None
    release_manifest_artifact_key: str | None = None
    preservation_mirrors: list[PreservationMirror] = Field(default_factory=list)
    certification: ArtifactCertification | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_artifact_identity(self) -> DataArtifact:
        if self.uri is None and not (self.path and self.repo_id and self.revision):
            raise ValueError("Data artifacts require uri or path/repo_id/revision.")
        if self.status in {"certified", "partially_certified", "hash_pinned"}:
            if self.sha256 is None:
                raise ValueError(
                    "Certified, partially certified, and hash-pinned data artifacts "
                    "require sha256."
                )
        if self.status in {"unverified", "unavailable"} and self.missing_reason is None:
            raise ValueError("Unverified/unavailable artifacts require missing_reason.")
        if self.status == "partially_certified":
            if self.certification is None:
                raise ValueError("Partially certified artifacts require certification.")
            if not self.certification.scopes:
                raise ValueError("Partially certified artifacts require scopes.")
            if not self.certification.limitations:
                raise ValueError("Partially certified artifacts require limitations.")
        return self


class CompatiblePackageSpecifier(BundleModel):
    name: str
    specifier: str


class DataBuildInfo(BundleModel):
    build_id: str | None = None
    built_at: str | None = None
    built_with_model_package: RuntimeComponentMetadata | None = None
    built_with_core_package: RuntimeComponentMetadata | PackagePin | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataReleaseManifest(BundleModel):
    schema_version: Literal[1]
    data_package: PackageIdentity
    compatible_model_packages: list[CompatiblePackageSpecifier] = Field(
        default_factory=list
    )
    compatible_core_packages: list[CompatiblePackageSpecifier] = Field(
        default_factory=list
    )
    default_datasets: dict[str, str] = Field(default_factory=dict)
    build: DataBuildInfo | None = None
    artifacts: dict[str, DataArtifact] = Field(default_factory=dict)
    preservation_dois: list[str] = Field(default_factory=list)
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateRuntimeCertification(BundleModel):
    basis: Literal["manual_runtime_certification"] = "manual_runtime_certification"
    certified_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: list[CertificationEvidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacyCandidateCountry(BundleModel):
    model_package: str
    data_release_manifest_uri: str
    certification: CandidateRuntimeCertification | None = None


class LegacyBundleCandidate(BundleModel):
    schema_version: Literal[1]
    bundle_version: str
    policyengine_version: str
    python_versions: list[str] = Field(min_length=1)
    profiles: list[str] = Field(min_length=1)
    packages: dict[str, str]
    countries: dict[str, LegacyCandidateCountry]

    @model_validator(mode="after")
    def validate_candidate(self) -> LegacyBundleCandidate:
        if self.policyengine_version != self.bundle_version:
            raise ValueError(
                "Legacy candidate policyengine_version must match bundle_version."
            )
        if "policyengine-core" not in self.packages:
            raise ValueError(
                "Legacy candidate packages must include policyengine-core."
            )
        if not self.countries:
            raise ValueError("Legacy candidate must include at least one country.")
        for country_id, country in self.countries.items():
            if country.model_package not in self.packages:
                raise ValueError(
                    f"Legacy country {country_id!r} references unknown model "
                    f"package {country.model_package!r}."
                )
        for profile in self.profiles:
            if profile != "all" and profile not in self.countries:
                raise ValueError(
                    f"Legacy profile {profile!r} must be 'all' or a country id."
                )
        return self


class CandidateCountry(BundleModel):
    model_package: str
    data_release_manifest_uri: str


class BundleCandidate(BundleModel):
    schema_version: Literal[2]
    bundle_version: str
    packages: dict[str, str]
    countries: dict[str, CandidateCountry]

    @model_validator(mode="after")
    def validate_candidate(self) -> BundleCandidate:
        _validate_exact_version(self.bundle_version, "bundle_version")
        if "policyengine" in self.packages:
            raise ValueError(
                "Candidate packages must not include policyengine; use "
                "bundle_version for the policyengine bundle carrier version."
            )
        if "policyengine-core" not in self.packages:
            raise ValueError("Candidate packages must include policyengine-core.")
        if not self.countries:
            raise ValueError("Candidate must include at least one country.")
        for package_name, package_version in self.packages.items():
            _validate_exact_version(
                package_version,
                f"packages[{package_name!r}]",
            )
        for country_id, country in self.countries.items():
            if country.model_package not in self.packages:
                raise ValueError(
                    f"Country {country_id!r} references unknown model package "
                    f"{country.model_package!r}."
                )
        return self


class RegionDataset(BundleModel):
    path_template: str
    uri_template: str | None = None


class LegacyInstallTarget(BundleModel):
    python_version: str
    constraints: str
    lockfile: str
    resolver: str = "uv"

    @model_validator(mode="after")
    def validate_bundle_paths(self) -> LegacyInstallTarget:
        _validate_relative_posix_path(self.constraints, "constraints")
        _validate_relative_posix_path(self.lockfile, "lockfile")
        return self


class LegacyCountryCertification(BundleModel):
    compatibility_basis: str
    built_with_model_package: PackagePin
    built_with_core_package: PackagePin
    certified_for_model_package: PackagePin
    certified_for_core_package: PackagePin
    certified_by: str
    data_build_id: str | None = None
    data_build_fingerprint: str | None = None
    runtime_model_package: RuntimeComponentMetadata | None = None
    runtime_core_package: RuntimeComponentMetadata | PackagePin | None = None
    evidence: list[CertificationEvidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacyCountryBundle(BundleModel):
    schema_version: Literal[1]
    bundle_version: str
    country_id: str
    model_package: PackagePin
    core_package: PackagePin
    data_package: DataPackageReference
    artifact_release: ArtifactRelease | None = None
    default_dataset: str
    datasets: dict[str, DataArtifact] = Field(min_length=1)
    region_datasets: dict[str, RegionDataset] = Field(default_factory=dict)
    certification: LegacyCountryCertification
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacyProfile(BundleModel):
    packages: list[str] = Field(min_length=1)
    countries: list[str] = Field(min_length=1)
    description: str | None = None
    install_targets: dict[str, LegacyInstallTarget] = Field(default_factory=dict)


class LegacyBundleManifest(BundleModel):
    schema_version: Literal[1]
    bundle_version: str
    policyengine: PackagePin
    packages: dict[str, PackagePin] = Field(min_length=1)
    profiles: dict[str, LegacyProfile] = Field(min_length=1)
    countries: dict[str, str] = Field(min_length=1)
    validation_report: str
    created_at: str | None = None
    bundle_digest: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompatibilityAssertion(BundleModel):
    basis: Literal["bundle_candidate"] = "bundle_candidate"
    model_package: PackagePin
    core_package: PackagePin
    data_package: PackageIdentity
    release_manifest_uri: str
    release_manifest_sha256: str
    asserted_by: str = "policyengine-bundles"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CountryBundle(BundleModel):
    schema_version: Literal[2]
    bundle_version: str
    country_id: str
    model_package: PackagePin
    core_package: PackagePin
    data_package: DataPackageReference
    artifact_release: ArtifactRelease
    default_dataset: str
    datasets: dict[str, DataArtifact] = Field(min_length=1)
    region_datasets: dict[str, RegionDataset] = Field(default_factory=dict)
    compatibility: CompatibilityAssertion
    metadata: dict[str, Any] = Field(default_factory=dict)


class BundleManifest(BundleModel):
    schema_version: Literal[2]
    bundle_version: str
    policyengine: PackagePin
    packages: dict[str, PackagePin] = Field(min_length=1)
    countries: dict[str, str] = Field(min_length=1)
    validation_report: str
    created_at: str | None = None
    bundle_digest: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegacyValidationCheck(BundleModel):
    name: str
    status: Literal["passed", "failed", "skipped"]
    profile: str | None = None
    country: str | None = None
    artifact: str | None = None
    python_version: str | None = None
    command: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    log_uri: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LegacyValidationReport(BundleModel):
    schema_version: Literal[1]
    bundle_version: str
    generated_at: str
    status: Literal["passed", "failed", "skipped"]
    checks: list[LegacyValidationCheck] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationCheck(BundleModel):
    name: str
    status: Literal["passed", "failed", "skipped"]
    country: str | None = None
    artifact: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BundleModel):
    schema_version: Literal[2]
    bundle_version: str
    generated_at: str
    status: Literal["passed", "failed", "skipped"]
    checks: list[ValidationCheck] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
