from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
KNOWN_HOSTS = {"claude-code", "codex", "opencode"}


class HostValidationError(RuntimeError):
    """Raised when a host task or result artifact violates the protocol."""


@dataclass(frozen=True)
class HostTask:
    command: str
    run_id: str
    host: str
    allowed_read_roots: list[str]
    allowed_write_roots: list[str]
    inputs: list[str]
    expected_output: str
    schema_version: int = SCHEMA_VERSION

    def write(self, task_dir: Path) -> Path:
        self._validate()
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / f"{self.command}-{self.host}.json"
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise HostValidationError(f"unsupported host task schema: {self.schema_version}")
        if self.host not in KNOWN_HOSTS:
            raise HostValidationError(f"unknown host: {self.host}")
        if not self.allowed_write_roots:
            raise HostValidationError("host task must declare allowed_write_roots")


@dataclass(frozen=True)
class HostResult:
    status: str
    host: str
    run_id: str
    output_path: str
    source_references: list[str]
    schema_version: int = SCHEMA_VERSION
    confidence: str | None = None
    errors: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "HostResult":
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = cls.from_dict(payload)
        result._validate()
        return result

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HostResult":
        return cls(
            schema_version=int(payload.get("schema_version", 0)),
            status=str(payload["status"]),
            host=str(payload["host"]),
            run_id=str(payload["run_id"]),
            output_path=str(payload["output_path"]),
            source_references=list(payload.get("source_references", [])),
            confidence=payload.get("confidence"),
            errors=list(payload.get("errors", [])),
        )

    def _validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise HostValidationError(f"unsupported host result schema: {self.schema_version}")
        if self.host not in KNOWN_HOSTS:
            raise HostValidationError(f"unknown host: {self.host}")
        if not self.source_references:
            raise HostValidationError("host result must include source_references")
