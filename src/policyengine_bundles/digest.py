from __future__ import annotations

import hashlib
from pathlib import Path

from policyengine_bundles.io import load_json, write_json
from policyengine_bundles.normalization import bundle_files, normalized_file_content
from policyengine_bundles.validation import load_bundle_directory


def compute_bundle_digest(bundle_dir: Path | str) -> str:
    """Compute the stable content digest for a bundle directory."""

    bundle = load_bundle_directory(bundle_dir)
    hasher = hashlib.sha256()
    for relative_path in sorted(bundle_files(bundle.root)):
        hasher.update(relative_path.as_posix().encode())
        hasher.update(b"\0")
        hasher.update(normalized_file_content(bundle.root, relative_path).encode())
        hasher.update(b"\0")
    return f"sha256:{hasher.hexdigest()}"


def write_bundle_digest(bundle_dir: Path | str) -> str:
    """Compute and persist ``bundle_digest`` in ``bundle.json``."""

    root = Path(bundle_dir)
    digest = compute_bundle_digest(root)
    manifest_path = root / "bundle.json"
    manifest = load_json(manifest_path)
    manifest["bundle_digest"] = digest
    write_json(manifest_path, manifest)
    return digest


def ensure_bundle_digest(bundle_dir: Path | str) -> str:
    """Write a missing digest, but reject an incorrect recorded digest."""

    root = Path(bundle_dir)
    manifest_path = root / "bundle.json"
    manifest = load_json(manifest_path)
    expected_digest = manifest.get("bundle_digest")
    actual_digest = compute_bundle_digest(root)
    if expected_digest is None:
        manifest["bundle_digest"] = actual_digest
        write_json(manifest_path, manifest)
        return actual_digest
    if expected_digest != actual_digest:
        raise ValueError(
            "bundle.json bundle_digest does not match bundle contents: "
            f"expected {expected_digest}, got {actual_digest}."
        )
    return actual_digest


def verify_bundle_digest(bundle_dir: Path | str) -> str:
    """Return the digest and fail when the manifest records a different value."""

    root = Path(bundle_dir)
    manifest = load_json(root / "bundle.json")
    expected_digest = manifest.get("bundle_digest")
    actual_digest = compute_bundle_digest(root)
    if expected_digest is not None and expected_digest != actual_digest:
        raise ValueError(
            "bundle.json bundle_digest does not match bundle contents: "
            f"expected {expected_digest}, got {actual_digest}."
        )
    return actual_digest


def verify_bundle_digests(bundles_root: Path | str) -> list[str]:
    """Verify committed bundle digests for active bundles.

    Schema v1 bundle directories are read-only historical artifacts and predate
    the committed ``bundle_digest`` field.
    """

    failures: list[str] = []
    for manifest_path in sorted(Path(bundles_root).glob("*/bundle.json")):
        bundle_dir = manifest_path.parent
        manifest = load_json(manifest_path)
        if manifest.get("schema_version") == 1:
            continue
        if "bundle_digest" not in manifest:
            failures.append(f"{bundle_dir}: missing bundle_digest")
            continue
        try:
            verify_bundle_digest(bundle_dir)
        except Exception as exc:
            failures.append(f"{bundle_dir}: {exc}")
    return failures
