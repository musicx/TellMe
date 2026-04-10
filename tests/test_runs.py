from __future__ import annotations

from pathlib import Path

from tellme.runs import RunStatus, RunStore


def test_run_store_creates_audit_directory_shape(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    run = store.start(command="lint", host="codex", inputs={"severity": "warning"})

    run_dir = tmp_path / "runs" / run.run_id
    assert (run_dir / "run.json").is_file()
    assert (run_dir / "input.json").is_file()
    assert (run_dir / "diagnostics.md").is_file()
    assert (run_dir / "host-tasks").is_dir()
    assert (run_dir / "artifacts").is_dir()


def test_run_store_supports_partial_and_cancelled_statuses(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    partial = store.start(command="compile", host="claude-code")
    cancelled = store.start(command="query", host="opencode")

    store.complete(partial.run_id, status=RunStatus.PARTIAL, outputs={"published": 1})
    store.complete(cancelled.run_id, status=RunStatus.CANCELLED)

    assert store.load(partial.run_id).status == RunStatus.PARTIAL
    assert store.load(cancelled.run_id).status == RunStatus.CANCELLED


def test_run_store_appends_diagnostics(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.start(command="ingest", host="codex")

    store.append_diagnostic(run.run_id, "source file missing")

    diagnostics = (tmp_path / "runs" / run.run_id / "diagnostics.md").read_text(
        encoding="utf-8"
    )
    assert "source file missing" in diagnostics
