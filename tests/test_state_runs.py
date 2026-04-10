from __future__ import annotations

import json
from pathlib import Path

from tellme.runs import RunStatus, RunStore
from tellme.state import ContentStatus, PageRecord, ProjectState, SourceRecord


def test_project_state_persists_registered_sources(tmp_path: Path) -> None:
    state = ProjectState.create(tmp_path / "state")
    source = SourceRecord.register(
        project_root=tmp_path,
        path=tmp_path / "raw" / "note.md",
        content="hello TellMe",
    )

    state.upsert_source(source)
    reloaded = ProjectState.load(tmp_path / "state")

    assert reloaded.get_source("raw/note.md") == source
    assert reloaded.get_source("raw/note.md").status == ContentStatus.REGISTERED


def test_project_state_persists_page_records(tmp_path: Path) -> None:
    state = ProjectState.create(tmp_path / "state")
    page = PageRecord(
        path="vault/wiki/Concepts/LLM Wiki.md",
        page_type="concept",
        status=ContentStatus.PUBLISHED,
        sha256="abc123",
        sources=["raw/note.md"],
        last_host="codex",
        last_run_id="20260410T000000Z-compile-12345678",
    )

    state.upsert_page(page)
    reloaded = ProjectState.load(tmp_path / "state")

    assert reloaded.get_page("vault/wiki/Concepts/LLM Wiki.md") == page


def test_run_store_creates_updateable_run_records(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")

    run = store.start(command="ingest", host="codex", inputs={"path": "raw/note.md"})
    store.complete(run.run_id, status=RunStatus.SUCCEEDED, outputs={"sources": 1})

    run_path = tmp_path / "runs" / run.run_id / "run.json"
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    reloaded = store.load(run.run_id)

    assert payload["command"] == "ingest"
    assert reloaded.status == RunStatus.SUCCEEDED
    assert reloaded.outputs == {"sources": 1}
    assert reloaded.completed_at is not None
