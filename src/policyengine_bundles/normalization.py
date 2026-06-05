from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from policyengine_bundles.io import load_json

IGNORED_FILE_NAMES = {".DS_Store"}


def bundle_files(root: Path) -> set[Path]:
    """Return bundle-relative files that are part of the release payload."""

    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and path.name not in IGNORED_FILE_NAMES
    }


def normalized_file_content(root: Path, relative_path: Path) -> str:
    path = root / relative_path
    if relative_path.suffix == ".json":
        payload = load_json(path)
        if relative_path.as_posix() == "bundle.json":
            payload = normalize_bundle_manifest(payload)
        elif relative_path.as_posix() == "validation-report.json":
            payload = normalize_validation_report(payload)
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return path.read_text()


def normalize_bundle_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized.pop("created_at", None)
    normalized.pop("bundle_digest", None)
    return normalized


def normalize_validation_report(payload: dict[str, Any]) -> dict[str, Any]:
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
