from __future__ import annotations

import json
from pathlib import Path

from tellme.compiler import compile_sources
from tellme.config import load_runtime
from tellme.ingest import ingest_file
from tellme.project import init_project
from tellme.reconcile import reconcile_vault
from tellme.runs import RunStore
from tellme.state import ContentStatus, ProjectState


def test_compile_publishes_registered_source_summary_and_records_state(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root)
    source = tmp_path / "outside.md"
    source.write_text("# Outside\n\nTellMe keeps source attribution.", encoding="utf-8")
    runs = RunStore(runtime.runs_dir)
    ingest_run = runs.start("ingest", "codex")
    source_record = ingest_file(runtime, source, ingest_run.run_id)
    compile_run = runs.start("compile", "codex")

    result = compile_sources(runtime=runtime, run_id=compile_run.run_id, host="codex")

    assert result.published_pages == ["wiki/sources/outside.md"]
    page_path = runtime.wiki_dir / "sources" / "outside.md"
    assert page_path.is_file()
    page_text = page_path.read_text(encoding="utf-8")
    assert "page_type: source_summary" in page_text
    assert "created_at:" in page_text
    assert "updated_at:" in page_text
    assert "raw/outside.md" in page_text
    assert "TellMe keeps source attribution." in page_text

    state = ProjectState.load(runtime.state_dir)
    page = state.get_page("wiki/sources/outside.md")
    assert page.status == ContentStatus.PUBLISHED
    assert page.sources == ["raw/outside.md"]
    assert state.get_source(source_record.path).status == ContentStatus.ANALYZED

    task_path = runtime.runs_dir / compile_run.run_id / "host-tasks" / "compile-codex.json"
    assert task_path.is_file()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    assert task["schema_version"] == 1
    assert task["allowed_write_roots"] == ["staging", "runs"]

    artifact_path = runtime.runs_dir / compile_run.run_id / "artifacts" / "compile-result.json"
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["published_pages"] == [
        "wiki/sources/outside.md"
    ]


def test_compile_records_file_hash_that_reconcile_does_not_treat_as_drift(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root)
    source = tmp_path / "outside.md"
    source.write_text("# Outside\n\nStable hash.", encoding="utf-8")
    runs = RunStore(runtime.runs_dir)
    ingest_run = runs.start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    compile_run = runs.start("compile", "codex")
    compile_sources(runtime=runtime, run_id=compile_run.run_id, host="codex")
    reconcile_run = runs.start("reconcile", "codex")

    result = reconcile_vault(runtime=runtime, run_id=reconcile_run.run_id, host="codex")

    assert result.changed_pages == []


def test_compile_stages_source_summary_when_publish_policy_disables_direct_publish(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    (project_root / "config" / "policies" / "publish.toml").write_text(
        "[publish]\nsource_summary_direct_publish = false\n",
        encoding="utf-8",
    )
    runtime = load_runtime(project_root=project_root)
    source = tmp_path / "outside.md"
    source.write_text("# Outside\n\nNeeds review.", encoding="utf-8")
    runs = RunStore(runtime.runs_dir)
    ingest_run = runs.start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    compile_run = runs.start("compile", "codex")

    result = compile_sources(runtime=runtime, run_id=compile_run.run_id, host="codex")

    assert result.published_pages == []
    assert result.staged_pages == ["staging/sources/outside.md"]
    assert not (runtime.wiki_dir / "sources" / "outside.md").exists()
    assert (runtime.staging_dir / "sources" / "outside.md").is_file()
    state = ProjectState.load(runtime.state_dir)
    assert state.get_page("staging/sources/outside.md").status == ContentStatus.STAGED
