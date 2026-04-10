from __future__ import annotations

from pathlib import Path

import pytest

from tellme.locks import LockAlreadyHeldError, ProjectLock
from tellme.runs import RunStatus, RunStore
from tellme.workflow import run_workflow


def test_project_lock_rejects_second_holder(tmp_path: Path) -> None:
    lock = ProjectLock(tmp_path)

    with lock.acquire("first-run"):
        with pytest.raises(LockAlreadyHeldError):
            with lock.acquire("second-run"):
                pass


def test_run_workflow_records_failed_run_when_operation_raises(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    with pytest.raises(ValueError):
        run_workflow(
            project_root=tmp_path,
            runs=store,
            command="lint",
            host="codex",
            inputs={"target": "vault"},
            operation=lambda run: (_ for _ in ()).throw(ValueError("boom")),
        )

    runs = list((tmp_path / "runs").iterdir())
    assert len(runs) == 1
    run = store.load(runs[0].name)
    assert run.status == RunStatus.FAILED
    assert "boom" in (runs[0] / "diagnostics.md").read_text(encoding="utf-8")


def test_run_workflow_records_successful_run(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    run = run_workflow(
        project_root=tmp_path,
        runs=store,
        command="lint",
        host="codex",
        inputs={"target": "vault"},
        operation=lambda run: {"issues": 0},
    )

    assert run.status == RunStatus.SUCCEEDED
    assert run.outputs == {"issues": 0}
