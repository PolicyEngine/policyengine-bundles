from __future__ import annotations

from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "open_policyengine_py_consuming_pr.sh"
)


def test_open_policyengine_py_consuming_pr_installs_policyengine_before_import() -> (
    None
):
    script = SCRIPT_PATH.read_text()

    install_position = script.index("python -m pip install --upgrade -e .")
    import_position = script.index("python scripts/import_policyengine_bundle.py")

    assert install_position < import_position


def test_open_policyengine_py_consuming_pr_uses_current_importer_cli() -> None:
    script = SCRIPT_PATH.read_text()

    assert "--archive" in script
    assert "../.tmp/dist/policyengine-bundle-$BUNDLE_VERSION.tar.gz" in script
    assert "--dist-dir" not in script
