from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from policyengine_bundles.io import load_json

IGNORED_FILE_NAMES = {".DS_Store"}


def compare_bundle_directories(
    expected_dir: Path | str,
    actual_dir: Path | str,
) -> list[str]:
    expected_root = Path(expected_dir)
    actual_root = Path(actual_dir)
    mismatches: list[str] = []
    if not expected_root.is_dir():
        mismatches.append(f"Expected bundle directory does not exist: {expected_root}")
    if not actual_root.is_dir():
        mismatches.append(f"Regenerated bundle directory does not exist: {actual_root}")
    if mismatches:
        return mismatches

    expected_files = _bundle_files(expected_root)
    actual_files = _bundle_files(actual_root)
    missing = sorted(set(expected_files).difference(actual_files))
    extra = sorted(set(actual_files).difference(expected_files))
    if missing:
        mismatches.append(
            "Missing files in regenerated bundle:\n"
            + "\n".join(f"- {path.as_posix()}" for path in missing)
        )
    if extra:
        mismatches.append(
            "Extra files in regenerated bundle:\n"
            + "\n".join(f"- {path.as_posix()}" for path in extra)
        )

    for relative_path in sorted(set(expected_files).intersection(actual_files)):
        expected_content = _normalized_file_content(expected_root, relative_path)
        actual_content = _normalized_file_content(actual_root, relative_path)
        if expected_content == actual_content:
            continue
        diff = "\n".join(
            difflib.unified_diff(
                expected_content.splitlines(),
                actual_content.splitlines(),
                fromfile=f"{expected_root / relative_path}",
                tofile=f"{actual_root / relative_path}",
                lineterm="",
            )
        )
        mismatches.append(f"{relative_path.as_posix()} differs:\n{diff}")

    return mismatches


def _bundle_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and path.name not in IGNORED_FILE_NAMES
    }


def _normalized_file_content(root: Path, relative_path: Path) -> str:
    path = root / relative_path
    if relative_path.suffix == ".json":
        payload = load_json(path)
        if relative_path.as_posix() == "bundle.json":
            payload = _normalize_bundle_manifest(payload)
        elif relative_path.as_posix() == "validation-report.json":
            payload = _normalize_validation_report(payload)
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return path.read_text()


def _normalize_bundle_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.pop("created_at", None)
    normalized.pop("bundle_digest", None)
    return normalized


def _normalize_validation_report(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.pop("generated_at", None)
    checks = []
    for check in normalized.get("checks", []):
        check_payload = dict(check)
        check_payload.pop("command", None)
        check_payload.pop("started_at", None)
        check_payload.pop("ended_at", None)
        details = check_payload.get("details")
        if isinstance(details, dict):
            details_payload = dict(details)
            details_payload.pop("validated_on_platform", None)
            details_payload.pop("bundle_dir", None)
            check_payload["details"] = details_payload
        checks.append(check_payload)
    normalized["checks"] = checks
    return normalized
