from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]


def load_json(path: Path) -> JsonDict:
    with path.open() as file:
        return json.load(file)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
