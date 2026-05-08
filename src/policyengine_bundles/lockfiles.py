from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from policyengine_bundles.io import write_json
from policyengine_bundles.models import BundleManifest, PackagePin
from policyengine_bundles.validation import load_bundle_directory

CommandRunner = Callable[[list[str]], None]
DEFAULT_PYTHON_PLATFORM = "linux"
DEFAULT_PYTHON_PLATFORMS = ("linux", "macos", "windows")


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True)


def solve_lockfiles(
    bundle_dir: Path | str,
    *,
    python_versions: Sequence[str] | None = None,
    python_platform: str | None = None,
    python_platforms: Sequence[str] | None = None,
    runner: CommandRunner = run_command,
) -> None:
    if python_platform is not None and python_platforms is not None:
        raise ValueError("Pass python_platform or python_platforms, not both.")
    bundle_root = Path(bundle_dir)
    bundle = load_bundle_directory(bundle_root)
    resolved_python_versions = list(
        python_versions or bundle.manifest.metadata.get("python_versions", [])
    )
    if not resolved_python_versions:
        raise ValueError(
            "No Python versions supplied. Pass --python-version or include "
            "metadata.python_versions in bundle.json."
        )
    resolved_python_platforms = _resolved_python_platforms(
        python_platform=python_platform,
        python_platforms=python_platforms,
    )

    manifest_payload = _load_bundle_manifest_payload(bundle_root)
    for profile_name, profile in bundle.manifest.profiles.items():
        _clear_profile_install_artifacts(manifest_payload, profile_name)
        direct_requirements = _direct_requirements(
            profile_name=profile_name,
            package_names=profile.packages,
            packages=bundle.manifest.packages,
        )
        for python_platform_value in resolved_python_platforms:
            for python_version in resolved_python_versions:
                _solve_install_target(
                    bundle_root=bundle_root,
                    manifest_payload=manifest_payload,
                    profile_name=profile_name,
                    python_version=python_version,
                    python_platform=python_platform_value,
                    direct_requirements=direct_requirements,
                    runner=runner,
                )

    manifest_payload.setdefault("metadata", {})["python_platforms"] = list(
        resolved_python_platforms
    )
    manifest_payload["metadata"]["install_artifact_layout"] = (
        "install/{profile}/{platform}-{python}/"
    )
    BundleManifest.model_validate(manifest_payload)
    write_json(bundle_root / "bundle.json", manifest_payload)
    load_bundle_directory(bundle_root)


def _resolved_python_platforms(
    *,
    python_platform: str | None,
    python_platforms: Sequence[str] | None,
) -> list[str]:
    if python_platform is not None:
        return [python_platform]
    return list(python_platforms or DEFAULT_PYTHON_PLATFORMS)


def _solve_install_target(
    *,
    bundle_root: Path,
    manifest_payload: dict,
    profile_name: str,
    python_version: str,
    python_platform: str,
    direct_requirements: list[str],
    runner: CommandRunner,
) -> None:
    target_key = install_target_key(
        python_platform=python_platform,
        python_version=python_version,
    )
    target_root = bundle_root / "install" / profile_name / target_key
    constraints_path = target_root / "constraints.txt"
    lockfile_path = target_root / "pylock.toml"
    target_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp_dir:
        requirements_path = Path(temp_dir) / "requirements.in"
        requirements_path.write_text("\n".join(direct_requirements) + "\n")
        runner(
            [
                "uv",
                "pip",
                "compile",
                str(requirements_path),
                "--python-version",
                python_version,
                "--python-platform",
                python_platform,
                "--format",
                "requirements.txt",
                "--generate-hashes",
                "--output-file",
                str(constraints_path),
            ]
        )
        runner(
            [
                "uv",
                "pip",
                "compile",
                str(requirements_path),
                "--python-version",
                python_version,
                "--python-platform",
                python_platform,
                "--format",
                "pylock.toml",
                "--output-file",
                str(lockfile_path),
            ]
        )
    _record_install_target(
        manifest_payload=manifest_payload,
        profile_name=profile_name,
        target_key=target_key,
        python_version=python_version,
        python_platform=python_platform,
        constraints_path=constraints_path.relative_to(bundle_root),
        lockfile_path=lockfile_path.relative_to(bundle_root),
    )


def python_version_key(python_version: str) -> str:
    parts = python_version.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError(
            f"Python version must use '<major>.<minor>' form, got {python_version!r}."
        )
    return f"py{parts[0]}{parts[1]}"


def install_target_key(*, python_platform: str, python_version: str) -> str:
    return (
        f"{python_platform_key(python_platform)}-{python_version_key(python_version)}"
    )


def python_platform_key(python_platform: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "-", python_platform.strip().lower()).strip("-")
    if not key:
        raise ValueError(f"Invalid Python platform: {python_platform!r}.")
    return key


def _direct_requirements(
    *,
    profile_name: str,
    package_names: Sequence[str],
    packages: dict[str, PackagePin],
) -> list[str]:
    requirements: list[str] = []
    for package_name in package_names:
        if package_name not in packages:
            raise ValueError(
                f"Profile {profile_name!r} references unknown package {package_name!r}."
            )
        pin = packages[package_name]
        if pin.version is None or pin.resolution_status != "pinned":
            raise ValueError(
                f"Profile {profile_name!r} package {package_name!r} must be "
                "exact-pinned before lockfile generation."
            )
        requirements.append(f"{pin.name}=={pin.version}")
    return requirements


def _load_bundle_manifest_payload(bundle_root: Path) -> dict:
    with (bundle_root / "bundle.json").open() as file:
        return json.load(file)


def _clear_profile_install_artifacts(
    manifest_payload: dict,
    profile_name: str,
) -> None:
    profile = manifest_payload["profiles"][profile_name]
    profile["install_targets"] = {}
    profile.pop("constraints", None)
    profile.pop("lockfiles", None)


def _record_install_target(
    *,
    manifest_payload: dict,
    profile_name: str,
    target_key: str,
    python_version: str,
    python_platform: str,
    constraints_path: Path,
    lockfile_path: Path,
) -> None:
    profile = manifest_payload["profiles"][profile_name]
    profile.setdefault("install_targets", {})[target_key] = {
        "python_version": python_version,
        "python_platform": python_platform,
        "constraints": constraints_path.as_posix(),
        "lockfile": lockfile_path.as_posix(),
        "resolver": "uv",
    }
