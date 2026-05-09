from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def python_version_key(python_version: str) -> str:
    parts = python_version.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(
            f"Python version must use '<major>.<minor>' form, got {python_version!r}."
        )
    return f"py{parts[0]}{parts[1]}"


def python_version_key_map(
    python_versions: Sequence[str],
    *,
    field_name: str = "python_versions",
) -> dict[str, str]:
    if not python_versions:
        raise ValueError(f"{field_name} must include at least one Python version.")

    keyed_versions: dict[str, str] = {}
    for python_version in python_versions:
        if not isinstance(python_version, str):
            raise ValueError(f"{field_name} entries must be strings.")
        target_key = python_version_key(python_version)
        if target_key in keyed_versions:
            raise ValueError(
                f"{field_name} contains duplicate Python target {target_key!r}."
            )
        keyed_versions[target_key] = python_version
    return keyed_versions


def metadata_python_versions(metadata: Mapping[str, Any]) -> list[str] | None:
    raw_python_versions = metadata.get("python_versions")
    if raw_python_versions is None:
        return None
    if not isinstance(raw_python_versions, list):
        raise ValueError("metadata.python_versions must be a list of strings.")
    python_version_key_map(
        raw_python_versions,
        field_name="metadata.python_versions",
    )
    return list(raw_python_versions)
