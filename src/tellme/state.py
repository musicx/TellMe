from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


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

    @classmethod
    def register(cls, project_root: Path, path: Path, content: str) -> "SourceRecord":
        return cls(
            path=_relative_posix(project_root=project_root, path=path),
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            status=ContentStatus.REGISTERED,
            registered_at=_utc_now(),
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceRecord":
        return cls(
            path=str(payload["path"]),
            sha256=str(payload["sha256"]),
            status=ContentStatus(str(payload["status"])),
            registered_at=str(payload["registered_at"]),
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
        return cls(state_dir=state_dir, payload=payload)

    def upsert_source(self, source: SourceRecord) -> None:
        self._payload.setdefault("sources", {})[source.path] = source.to_dict()
        self._save()

    def get_source(self, path: str) -> SourceRecord:
        return SourceRecord.from_dict(self._payload["sources"][path])

    def upsert_page(self, page: PageRecord) -> None:
        self._payload.setdefault("pages", {})[page.path] = page.to_dict()
        self._save()

    def get_page(self, path: str) -> PageRecord:
        return PageRecord.from_dict(self._payload["pages"][path])

    def _save(self) -> None:
        self.manifest_path.write_text(
            json.dumps(self._payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _empty_manifest() -> dict[str, Any]:
    return {"version": 1, "sources": {}, "pages": {}}


def _relative_posix(project_root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        relative = path
    return relative.as_posix()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
