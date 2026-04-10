from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .locks import ProjectLock
from .runs import RunRecord, RunStatus, RunStore


def run_workflow(
    project_root: Path,
    runs: RunStore,
    command: str,
    host: str,
    inputs: dict[str, Any] | None,
    operation: Callable[[RunRecord], dict[str, Any] | None],
) -> RunRecord:
    run = runs.start(command=command, host=host, inputs=inputs)
    lock = ProjectLock(project_root)
    try:
        with lock.acquire(run.run_id):
            outputs = operation(run) or {}
    except Exception as exc:
        runs.append_diagnostic(run.run_id, str(exc))
        runs.complete(run.run_id, status=RunStatus.FAILED, outputs={"error": str(exc)})
        raise
    return runs.complete(run.run_id, status=RunStatus.SUCCEEDED, outputs=outputs)
