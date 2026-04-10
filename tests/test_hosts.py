from __future__ import annotations

import json
from pathlib import Path

import pytest

from tellme.hosts import HostResult, HostTask, HostValidationError
from tellme.runs import RunStore


def test_host_task_packet_is_written_with_schema_version_and_allowed_roots(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.start("compile", "codex")
    task = HostTask(
        command="compile",
        run_id=run.run_id,
        host="codex",
        allowed_read_roots=["raw", "vault"],
        allowed_write_roots=["staging", "runs"],
        inputs=["raw/note.md"],
        expected_output="artifacts/compile-result.json",
    )

    path = task.write(store.host_tasks_dir(run.run_id))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["host"] == "codex"
    assert payload["allowed_write_roots"] == ["staging", "runs"]


def test_host_task_rejects_unknown_host(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.start("compile", "codex")

    with pytest.raises(HostValidationError):
        HostTask(
            command="compile",
            run_id=run.run_id,
            host="unknown",
            allowed_read_roots=["raw"],
            allowed_write_roots=["staging"],
            inputs=[],
            expected_output="artifacts/result.json",
        ).write(store.host_tasks_dir(run.run_id))


def test_host_result_requires_source_references(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "run-1",
                "output_path": "staging/page.md",
                "source_references": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HostValidationError):
        HostResult.load(result_path)
