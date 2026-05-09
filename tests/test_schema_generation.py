from __future__ import annotations

import json
from pathlib import Path

from policyengine_bundles.schema_generation import generated_schema_documents


def test_committed_schemas_are_generated_from_models() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    schema_dir = repo_root / "schemas"
    expected = generated_schema_documents()
    actual = {
        path.name: json.loads(path.read_text())
        for path in sorted(schema_dir.glob("*.schema.json"))
    }

    assert actual == expected
