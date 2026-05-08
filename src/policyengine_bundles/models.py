from __future__ import annotations

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


class PackageIdentity(BundleModel):
    name: str
    version: str


class PackagePin(BundleModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["version"],
                    "properties": {"version": {"type": "string"}},
                },
                {
                    "required": ["specifier"],
                    "properties": {"specifier": {"type": "string"}},
                },
            ]
        },
    )

    name: str
    version: str | None = None
    specifier: str | None = None
    resolution_status: Literal["pinned", "specifier_only", "unresolved"] | None = None
    wheel_url: str | None = None
    sdist_url: str | None = None
    sha256: str | None = None
    git_sha: str | None = None
    source: str | None = None

    @model_validator(mode="after")
    def require_version_or_specifier(self) -> PackagePin:
        if self.version is None and self.specifier is None:
            raise ValueError("Package pins require either version or specifier.")
        return self


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
    release_manifest_uri: str | None = None
    release_manifest_sha256: str | None = None


class PreservationMirror(BundleModel):
    kind: str
    url: str
    doi: str | None = None
    sha256: str | None = None
    deposited_at: str | None = None


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
                        "properties": {"status": {"const": "certified"}},
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
            ],
        },
    )

    kind: str
    uri: str | None = None
    path: str | None = None
    repo_id: str | None = None
    revision: str | None = None
    status: Literal["certified", "unverified", "unavailable"] = "certified"
    sha256: str | None = None
    missing_reason: str | None = None
    size_bytes: int | None = None
    release_manifest_artifact_key: str | None = None
    preservation_mirrors: list[PreservationMirror] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_artifact_identity(self) -> DataArtifact:
        if self.uri is None and not (self.path and self.repo_id and self.revision):
            raise ValueError("Data artifacts require uri or path/repo_id/revision.")
        if self.status == "certified" and self.sha256 is None:
            raise ValueError("Certified data artifacts require sha256.")
        if self.status != "certified" and self.missing_reason is None:
            raise ValueError("Unverified/unavailable artifacts require missing_reason.")
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
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegionDataset(BundleModel):
    path_template: str
    uri_template: str | None = None


class InstallTarget(BundleModel):
    python_version: str
    constraints: str
    lockfile: str
    resolver: str = "uv"

    @model_validator(mode="after")
    def validate_bundle_paths(self) -> InstallTarget:
        _validate_relative_posix_path(self.constraints, "constraints")
        _validate_relative_posix_path(self.lockfile, "lockfile")
        return self


class CountryCertification(BundleModel):
    compatibility_basis: str
    built_with_model_package: PackagePin
    built_with_core_package: PackagePin
    certified_for_model_package: PackagePin
    certified_for_core_package: PackagePin
    certified_by: str
    data_build_id: str | None = None
    data_build_fingerprint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CountryBundle(BundleModel):
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
    certification: CountryCertification
    metadata: dict[str, Any] = Field(default_factory=dict)


class Profile(BundleModel):
    packages: list[str] = Field(min_length=1)
    countries: list[str] = Field(min_length=1)
    description: str | None = None
    install_targets: dict[str, InstallTarget] = Field(default_factory=dict)


class BundleManifest(BundleModel):
    schema_version: Literal[1]
    bundle_version: str
    policyengine: PackagePin
    packages: dict[str, PackagePin] = Field(min_length=1)
    profiles: dict[str, Profile] = Field(min_length=1)
    countries: dict[str, str] = Field(min_length=1)
    validation_report: str
    created_at: str | None = None
    bundle_digest: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationCheck(BundleModel):
    name: str
    status: Literal["passed", "failed", "skipped"]
    profile: str | None = None
    country: str | None = None
    python_version: str | None = None
    command: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    log_uri: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BundleModel):
    schema_version: Literal[1]
    bundle_version: str
    generated_at: str
    status: Literal["passed", "failed", "skipped"]
    checks: list[ValidationCheck] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
