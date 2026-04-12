from __future__ import annotations

import json
from pathlib import Path

from tellme.config import load_runtime
from tellme.ingest import ingest_file
from tellme.project import init_project
from tellme.runs import RunStore
from tellme.state import ContentStatus, ProjectState


def test_ingest_file_copies_external_source_into_raw_and_registers_state(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    external = tmp_path / "note.md"
    external.write_text("# Note\n\nHello TellMe\n", encoding="utf-8")
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    run = RunStore(runtime.runs_dir).start("ingest", "codex")

    source = ingest_file(runtime=runtime, source_path=external, run_id=run.run_id)

    assert source.path == "raw/note.md"
    assert (runtime.raw_dir / "note.md").read_text(encoding="utf-8") == "# Note\n\nHello TellMe\n"
    reloaded = ProjectState.load(runtime.state_dir).get_source("raw/note.md")
    assert reloaded.status == ContentStatus.REGISTERED
    assert reloaded.registration_run_id == run.run_id


def test_ingest_file_uses_collision_safe_raw_name(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    external = tmp_path / "note.md"
    external.write_text("external", encoding="utf-8")
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    (runtime.raw_dir / "note.md").write_text("existing", encoding="utf-8")
    run = RunStore(runtime.runs_dir).start("ingest", "codex")

    source = ingest_file(runtime=runtime, source_path=external, run_id=run.run_id)

    assert source.path == "raw/note-1.md"
    assert (runtime.raw_dir / "note.md").read_text(encoding="utf-8") == "existing"
    assert (runtime.raw_dir / "note-1.md").read_text(encoding="utf-8") == "external"


def test_cli_ingest_missing_file_records_failed_run(tmp_path: Path, monkeypatch) -> None:
    from test_cli import run_cli
    from tellme.config import load_runtime

    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    runtime_root = tmp_path / "tellme-runtime"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    monkeypatch.setenv("TELLME_RUNTIME_ROOT", str(runtime_root))
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "ingest", str(tmp_path / "missing.md"), cwd=tmp_path)

    assert result.returncode != 0
    runtime = load_runtime(project_root=project_root)
    run_dirs = list(runtime.runs_dir.glob("*/run.json"))
    assert len(run_dirs) == 1
    payload = json.loads(run_dirs[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
