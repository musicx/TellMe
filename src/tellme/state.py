from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from .files import atomic_write_json


class StateFormatError(RuntimeError):
    """Raised when the project manifest cannot be interpreted safely."""


class ContentStatus(StrEnum):
    RAW = "raw"
    REGISTERED = "registered"
    ANALYZED = "analyzed"
    STAGED = "staged"
    PUBLISHED = "published"
    RECONCILED = "reconciled"


@dataclass(frozen=True)
class SourceRecord:
    path: str
    sha256: str
    status: ContentStatus
    registered_at: str
    source_type: str = "file"
    raw_path: str | None = None
    original_path: str | None = None
    registration_run_id: str | None = None

    @classmethod
    def register(
        cls,
        project_root: Path,
        path: Path,
        content: str,
        registration_run_id: str | None = None,
    ) -> "SourceRecord":
        relative = _relative_posix(project_root=project_root, path=path)
        return cls(
            path=relative,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            status=ContentStatus.REGISTERED,
            registered_at=_utc_now(),
            raw_path=relative,
            original_path=relative,
            registration_run_id=registration_run_id,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceRecord":
        return cls(
            path=str(payload["path"]),
            sha256=str(payload["sha256"]),
            status=ContentStatus(str(payload["status"])),
            registered_at=str(payload["registered_at"]),
            source_type=str(payload.get("source_type", "file")),
            raw_path=payload.get("raw_path"),
            original_path=payload.get("original_path"),
            registration_run_id=payload.get("registration_run_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class PageRecord:
    path: str
    page_type: str
    status: ContentStatus
    sha256: str
    sources: list[str]
    last_host: str
    last_run_id: str
    published_path: str | None = None
    staged_path: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PageRecord":
        return cls(
            path=str(payload["path"]),
            page_type=str(payload["page_type"]),
            status=ContentStatus(str(payload["status"])),
            sha256=str(payload["sha256"]),
            sources=list(payload.get("sources", [])),
            last_host=str(payload["last_host"]),
            last_run_id=str(payload["last_run_id"]),
            published_path=payload.get("published_path"),
            staged_path=payload.get("staged_path"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


class ProjectState:
    def __init__(self, state_dir: Path, payload: dict[str, Any]) -> None:
        self.state_dir = state_dir
        self.manifest_path = state_dir / "manifest.json"
        self._payload = payload

    @property
    def schema_version(self) -> int:
        return int(self._payload["schema_version"])

    @classmethod
    def create(cls, state_dir: Path) -> "ProjectState":
        state_dir.mkdir(parents=True, exist_ok=True)
        state = cls(state_dir=state_dir, payload=_empty_manifest())
        if not state.manifest_path.exists():
            state._save()
        return cls.load(state_dir)

    @classmethod
    def load(cls, state_dir: Path) -> "ProjectState":
        manifest_path = state_dir / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        normalized = _normalize_manifest(payload)
        state = cls(state_dir=state_dir, payload=normalized)
        if normalized != payload:
            state._save()
        return state

    def upsert_source(self, source: SourceRecord) -> None:
        self._payload.setdefault("sources", {})[source.path] = source.to_dict()
        self._save()

    def get_source(self, path: str) -> SourceRecord:
        return SourceRecord.from_dict(self._payload["sources"][path])

    def sources(self) -> dict[str, dict[str, Any]]:
        return dict(self._payload.get("sources", {}))

    def upsert_page(self, page: PageRecord) -> None:
        self._payload.setdefault("pages", {})[page.path] = page.to_dict()
        self._save()

    def get_page(self, path: str) -> PageRecord:
        return PageRecord.from_dict(self._payload["pages"][path])

    def pages(self) -> dict[str, dict[str, Any]]:
        return dict(self._payload.get("pages", {}))

    def _save(self) -> None:
        atomic_write_json(self.manifest_path, self._payload)


def _empty_manifest() -> dict[str, Any]:
    return {"schema_version": 1, "sources": {}, "pages": {}, "links": {}, "indexes": {}}


def _normalize_manifest(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise StateFormatError("manifest.json must contain a JSON object")
    normalized = dict(payload)
    if "schema_version" not in normalized and "version" in normalized:
        normalized["schema_version"] = normalized.pop("version")
    if "schema_version" not in normalized:
        raise StateFormatError("manifest.json is missing schema_version")
    for key in ("sources", "pages", "links", "indexes"):
        value = normalized.setdefault(key, {})
        if not isinstance(value, dict):
            raise StateFormatError(f"manifest.json field {key} must be an object")
    return normalized


def _relative_posix(project_root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        relative = path
    return relative.as_posix()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
