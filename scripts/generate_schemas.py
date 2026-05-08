from __future__ import annotations

from pathlib import Path

from policyengine_bundles.schema_generation import write_schema_documents

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schemas"


def main() -> int:
    write_schema_documents(SCHEMA_DIR)
    for schema_path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        print(f"generated schema: {schema_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
