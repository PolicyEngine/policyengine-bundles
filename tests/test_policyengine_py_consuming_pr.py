from __future__ import annotations

import importlib.util
import json
import tarfile
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "should_open_policyengine_py_consuming_pr.py"
)
SPEC = importlib.util.spec_from_file_location(
    "should_open_policyengine_py_consuming_pr", SCRIPT_PATH
)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
load_bundle_manifest = MODULE.load_release_bundle_manifest
should_open_pr = MODULE.should_open_policyengine_py_consuming_pr


def test__given_us_only_bundle__then_skips_policyengine_py_pr() -> None:
    bundle = {
        "bundle_version": "4.14.0",
        "packages": {
            "policyengine-core": {"version": "3.26.1"},
            "policyengine-us": {"version": "1.715.3"},
        },
    }

    should_open, reason = should_open_pr(bundle)

    assert should_open is False
    assert "policyengine-uk" in reason


def test__given_all_country_bundle__then_opens_policyengine_py_pr() -> None:
    bundle = {
        "bundle_version": "4.14.0",
        "packages": {
            "policyengine-core": {"version": "3.26.1"},
            "policyengine-uk": {"version": "2.88.20"},
            "policyengine-us": {"version": "1.715.3"},
        },
    }

    should_open, reason = should_open_pr(bundle)

    assert should_open is True
    assert "all packages" in reason


def test__given_release_archive__then_reads_bundle_manifest(tmp_path: Path) -> None:
    version = "4.14.0"
    dist_dir = tmp_path / "dist"
    bundle_root = tmp_path / f"policyengine-bundle-{version}"
    bundle_root.mkdir()
    (bundle_root / "bundle.json").write_text(
        json.dumps({"bundle_version": version, "packages": {}})
    )
    dist_dir.mkdir()
    archive_path = dist_dir / f"policyengine-bundle-{version}.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(bundle_root, arcname=bundle_root.name)

    bundle = load_bundle_manifest(version=version, dist_dir=dist_dir)

    assert bundle["bundle_version"] == version
