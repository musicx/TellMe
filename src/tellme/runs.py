from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    command: str
    host: str
    status: RunStatus
    started_at: str
    completed_at: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunRecord":
        return cls(
            run_id=str(payload["run_id"]),
            command=str(payload["command"]),
            host=str(payload["host"]),
            status=RunStatus(str(payload["status"])),
            started_at=str(payload["started_at"]),
            completed_at=payload.get("completed_at"),
            inputs=dict(payload.get("inputs", {})),
            outputs=dict(payload.get("outputs", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


class RunStore:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def start(self, command: str, host: str, inputs: dict[str, Any] | None = None) -> RunRecord:
        run = RunRecord(
            run_id=_new_run_id(command),
            command=command,
            host=host,
            status=RunStatus.RUNNING,
            started_at=_utc_now(),
            inputs=inputs or {},
        )
        self._write(run)
        return run

    def complete(
        self,
        run_id: str,
        status: RunStatus,
        outputs: dict[str, Any] | None = None,
    ) -> RunRecord:
        current = self.load(run_id)
        completed = RunRecord(
            run_id=current.run_id,
            command=current.command,
            host=current.host,
            status=status,
            started_at=current.started_at,
            completed_at=_utc_now(),
            inputs=current.inputs,
            outputs=outputs or {},
        )
        self._write(completed)
        return completed

    def load(self, run_id: str) -> RunRecord:
        payload = json.loads((self.runs_dir / run_id / "run.json").read_text(encoding="utf-8"))
        return RunRecord.from_dict(payload)

    def host_tasks_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "host-tasks"

    def artifacts_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id / "artifacts"

    def _write(self, run: RunRecord) -> None:
        run_dir = self.runs_dir / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "host-tasks").mkdir(exist_ok=True)
        (run_dir / "artifacts").mkdir(exist_ok=True)
        input_path = run_dir / "input.json"
        if not input_path.exists():
            input_path.write_text(
                json.dumps(run.inputs, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        diagnostics_path = run_dir / "diagnostics.md"
        if not diagnostics_path.exists():
            diagnostics_path.write_text("", encoding="utf-8")
        (run_dir / "run.json").write_text(
            json.dumps(run.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def append_diagnostic(self, run_id: str, message: str) -> None:
        diagnostics_path = self.runs_dir / run_id / "diagnostics.md"
        diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
        existing = diagnostics_path.read_text(encoding="utf-8") if diagnostics_path.exists() else ""
        diagnostics_path.write_text(existing + message + "\n", encoding="utf-8")


def _new_run_id(command: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}-{command}-{suffix}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
