from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path

from policyengine_bundles.digest import ensure_bundle_digest
from policyengine_bundles.io import write_json
from policyengine_bundles.models import ValidationCheck, ValidationReport
from policyengine_bundles.normalization import bundle_files
from policyengine_bundles.validation import BundleDirectory, load_bundle_directory

ARCHIVE_MEMBER_MTIME = 0


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


def _validate_release_ready(bundle: BundleDirectory) -> None:
    report = bundle.validation_report
    if report.status != "passed":
        raise ValueError(
            "Bundle release artifacts require a passing validation report; "
            f"got {report.status!r}."
        )
    if report.metadata.get("validation_scope") != "full":
        raise ValueError(
            "Bundle release artifacts require validation_scope='full'; "
            f"got {report.metadata.get('validation_scope')!r}."
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
    if check.profile:
        parts.append(f"profile={check.profile}")
    if check.country:
        parts.append(f"country={check.country}")
    if check.python_version:
        parts.append(f"python={check.python_version}")
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
