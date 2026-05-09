from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Literal

RepoType = Literal["model", "dataset", "space"]


def hugging_face_token() -> str | None:
    """Return the first supported Hugging Face token environment variable."""
    return (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("HUGGING_FACE_TOKEN")
    )


@dataclass(frozen=True)
class HuggingFaceReference:
    repo_type: RepoType
    repo_id: str
    revision: str
    path: str

    @classmethod
    def parse(cls, uri: str) -> HuggingFaceReference:
        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme != "hf":
            raise ValueError(f"Expected hf:// URI, got {uri!r}.")

        repo_type, rest = _repo_type_and_reference(parsed)
        repo_id, revision, path = _parse_reference_parts(rest)
        return cls(
            repo_type=repo_type,
            repo_id=repo_id,
            revision=revision,
            path=path,
        )

    def to_uri(self) -> str:
        return f"hf://{self.repo_type}/{self.repo_id}@{self.revision}/{self.path}"

    def download_url(self) -> str:
        prefix = {
            "model": "",
            "dataset": "datasets/",
            "space": "spaces/",
        }[self.repo_type]
        quoted_path = "/".join(
            urllib.parse.quote(part) for part in self.path.split("/")
        )
        return (
            f"https://huggingface.co/{prefix}{self.repo_id}/resolve/"
            f"{urllib.parse.quote(self.revision)}/{quoted_path}"
        )


def _repo_type_and_reference(
    parsed: urllib.parse.ParseResult,
) -> tuple[RepoType, str]:
    if parsed.netloc == "model":
        return "model", parsed.path.lstrip("/")
    if parsed.netloc == "dataset":
        return "dataset", parsed.path.lstrip("/")
    if parsed.netloc == "space":
        return "space", parsed.path.lstrip("/")
    return "model", f"{parsed.netloc}{parsed.path}"


def _parse_reference_parts(rest: str) -> tuple[str, str, str]:
    if "@" not in rest:
        raise ValueError(
            "HF URIs must include an immutable revision, for example "
            "hf://model/org/repo@version/path."
        )

    repo_id, revision_and_path = rest.split("@", 1)
    if "/" in revision_and_path:
        revision, path = revision_and_path.split("/", 1)
        if repo_id and revision and path:
            return repo_id, revision, path

    repo_and_path, revision = rest.rsplit("@", 1)
    parts = repo_and_path.split("/")
    if len(parts) < 3:
        raise ValueError("Legacy HF URIs must use hf://org/repo/path@revision form.")
    repo_id = "/".join(parts[:2])
    path = "/".join(parts[2:])
    if not repo_id or not revision or not path:
        raise ValueError(f"Incomplete HF URI reference: {rest!r}.")
    return repo_id, revision, path
