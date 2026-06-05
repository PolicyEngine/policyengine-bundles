from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

from policyengine_bundles.digest import ensure_bundle_digest, verify_bundle_digest
from policyengine_bundles.io import write_json
from policyengine_bundles.models import ValidationCheck, ValidationReport
from policyengine_bundles.normalization import bundle_files
from policyengine_bundles.validation import BundleDirectory, load_bundle_directory

ARCHIVE_MEMBER_MTIME = 0
DEFAULT_RELEASE_BASE_URL = (
    "https://github.com/PolicyEngine/policyengine-bundles/releases/download"
)


def package_bundle_release(bundle_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    bundle = load_bundle_directory(bundle_dir)
    _validate_release_ready(bundle)
    if bundle.root.name != bundle.manifest.bundle_version:
        raise ValueError(
            "Bundle directory name must match bundle_version: "
            f"{bundle.root.name!r} != {bundle.manifest.bundle_version!r}."
        )

    digest = ensure_bundle_digest(bundle.root)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = (
        output_dir / f"policyengine-bundle-{bundle.manifest.bundle_version}.tar.gz"
    )
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")

    _write_reproducible_tar_gz(
        source_dir=bundle.root,
        archive_root=f"policyengine-bundle-{bundle.manifest.bundle_version}",
        archive_path=archive_path,
    )
    checksum = _sha256_file(archive_path)
    checksum_path.write_text(f"{checksum}  {archive_path.name}\n")

    write_json(
        output_dir / f"policyengine-bundle-{bundle.manifest.bundle_version}.json",
        {
            "bundle_version": bundle.manifest.bundle_version,
            "bundle_digest": digest,
            "archive": archive_path.name,
            "archive_sha256": checksum,
        },
    )
    return archive_path, checksum_path


def fetch_bundle_release(
    *,
    version: str,
    output_dir: Path,
    base_url: str = DEFAULT_RELEASE_BASE_URL,
) -> Path:
    """Download, verify, and unpack a published bundle release."""

    with TemporaryDirectory() as temp_dir:
        dist_dir = Path(temp_dir)
        for asset_name in _release_asset_names(version):
            _download_asset(
                url=f"{base_url.rstrip('/')}/v{version}/{asset_name}",
                output_path=dist_dir / asset_name,
            )
        return verify_and_unpack_bundle_release(
            version=version,
            dist_dir=dist_dir,
            output_dir=output_dir,
        )


def verify_and_unpack_bundle_release(
    *,
    version: str,
    dist_dir: Path,
    output_dir: Path,
) -> Path:
    """Verify local release assets and unpack the bundle archive."""

    archive_path, summary = verify_bundle_release_assets(
        version=version,
        dist_dir=dist_dir,
    )
    bundle_dir = _extract_bundle_archive(
        archive_path=archive_path,
        output_dir=output_dir,
        version=version,
    )
    actual_digest = verify_bundle_digest(bundle_dir)
    expected_digest = summary.get("bundle_digest")
    if expected_digest != actual_digest:
        raise ValueError(
            "Release summary bundle_digest does not match unpacked bundle: "
            f"expected {expected_digest}, got {actual_digest}."
        )
    return bundle_dir


def verify_bundle_release_assets(
    *,
    version: str,
    dist_dir: Path,
) -> tuple[Path, dict]:
    """Verify the archive, checksum file, and summary JSON for a release."""

    archive_name, checksum_name, summary_name = _release_asset_names(version)
    archive_path = dist_dir / archive_name
    checksum_path = dist_dir / checksum_name
    summary_path = dist_dir / summary_name
    missing = [
        path.name
        for path in (archive_path, checksum_path, summary_path)
        if not path.exists()
    ]
    if missing:
        raise ValueError(f"Missing bundle release assets: {', '.join(missing)}.")

    with summary_path.open() as file:
        summary = json.load(file)
    if summary.get("bundle_version") != version:
        raise ValueError(
            "Release summary bundle_version does not match requested version: "
            f"expected {version}, got {summary.get('bundle_version')}."
        )
    if summary.get("archive") != archive_name:
        raise ValueError(
            "Release summary archive name does not match expected asset: "
            f"expected {archive_name}, got {summary.get('archive')}."
        )

    checksum = _read_checksum_file(checksum_path, archive_name)
    summary_checksum = summary.get("archive_sha256")
    if summary_checksum != checksum:
        raise ValueError(
            "Release summary archive_sha256 does not match checksum file: "
            f"expected {summary_checksum}, got {checksum}."
        )
    actual_checksum = _sha256_file(archive_path)
    if actual_checksum != checksum:
        raise ValueError(
            "Archive sha256 does not match checksum file: "
            f"expected {checksum}, got {actual_checksum}."
        )
    return archive_path, summary


def _validate_release_ready(bundle: BundleDirectory) -> None:
    report = bundle.validation_report
    if report.status != "passed":
        raise ValueError(
            "Bundle release artifacts require a passing validation report; "
            f"got {report.status!r}."
        )
    if report.metadata.get("validation_kind") != "registry":
        raise ValueError(
            "Bundle release artifacts require registry validation; "
            f"got {report.metadata.get('validation_kind')!r}."
        )
    skipped_checks = _checks_with_status(report, "skipped")
    if skipped_checks:
        raise ValueError(
            "Bundle release artifacts require no skipped validation checks; "
            f"skipped checks: {', '.join(skipped_checks)}."
        )
    failed_checks = _checks_with_status(report, "failed")
    if failed_checks:
        raise ValueError(
            "Bundle release artifacts require no failed validation checks; "
            f"failed checks: {', '.join(failed_checks)}."
        )


def _checks_with_status(report: ValidationReport, status: str) -> list[str]:
    return [_check_label(check) for check in report.checks if check.status == status]


def _check_label(check: ValidationCheck) -> str:
    parts = [check.name]
    if check.country:
        parts.append(f"country={check.country}")
    if check.artifact:
        parts.append(f"artifact={check.artifact}")
    return " ".join(parts)


def _write_reproducible_tar_gz(
    *,
    source_dir: Path,
    archive_root: str,
    archive_path: Path,
) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for relative_path in sorted(bundle_files(source_dir)):
            path = source_dir / relative_path
            info = tar.gettarinfo(
                name=path,
                arcname=str(Path(archive_root) / relative_path),
            )
            info.mtime = ARCHIVE_MEMBER_MTIME
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as file:
                tar.addfile(info, file)

    with archive_path.open("wb") as raw_file:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_file,
            mtime=ARCHIVE_MEMBER_MTIME,
        ) as gzip_file:
            gzip_file.write(buffer.getvalue())


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _release_asset_names(version: str) -> tuple[str, str, str]:
    archive_name = f"policyengine-bundle-{version}.tar.gz"
    return archive_name, f"{archive_name}.sha256", f"policyengine-bundle-{version}.json"


def release_asset_names(version: str) -> tuple[str, str, str]:
    return _release_asset_names(version)


def _download_asset(*, url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response:
        output_path.write_bytes(response.read())


def _read_checksum_file(path: Path, archive_name: str) -> str:
    text = path.read_text().strip()
    parts = text.split()
    if len(parts) != 2:
        raise ValueError(f"Invalid checksum file format: {path}.")
    checksum, filename = parts
    if filename != archive_name:
        raise ValueError(
            "Checksum file archive name does not match expected asset: "
            f"expected {archive_name}, got {filename}."
        )
    return checksum


def _extract_bundle_archive(
    *,
    archive_path: Path,
    output_dir: Path,
    version: str,
) -> Path:
    expected_root = f"policyengine-bundle-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path) as archive:
        for member in archive.getmembers():
            member_path = Path(member.name)
            if (
                member_path.is_absolute()
                or ".." in member_path.parts
                or member_path.parts[:1] != (expected_root,)
            ):
                raise ValueError(f"Unsafe bundle archive member: {member.name}.")
        archive.extractall(output_dir, filter="data")
    return output_dir / expected_root
