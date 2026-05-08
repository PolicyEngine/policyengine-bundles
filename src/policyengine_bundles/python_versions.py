from __future__ import annotations


def python_version_key(python_version: str) -> str:
    parts = python_version.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(
            f"Python version must use '<major>.<minor>' form, got {python_version!r}."
        )
    return f"py{parts[0]}{parts[1]}"
