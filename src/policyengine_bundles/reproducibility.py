from __future__ import annotations

import difflib
from pathlib import Path

from policyengine_bundles.normalization import bundle_files, normalized_file_content


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

    expected_files = bundle_files(expected_root)
    actual_files = bundle_files(actual_root)
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
        expected_content = normalized_file_content(expected_root, relative_path)
        actual_content = normalized_file_content(actual_root, relative_path)
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
