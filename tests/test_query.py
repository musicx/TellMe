from __future__ import annotations

from pathlib import Path

from tellme.config import load_runtime
from tellme.project import init_project
from tellme.query import query_vault
from tellme.runs import RunStore
from tellme.state import ProjectState


def test_query_reads_vault_first_and_writes_run_artifact(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root)
    page = runtime.vault_dir / "alpha.md"
    page.write_text(
        "---\npage_type: note\nsources:\n  - raw/source.md\n---\n# Alpha\n\nLLM wiki context.",
        encoding="utf-8",
    )
    run = RunStore(runtime.runs_dir).start("query", "codex")

    result = query_vault(
        runtime=runtime,
        question="What says alpha?",
        run_id=run.run_id,
        host="codex",
        stage=False,
    )

    assert result.answer_path == f"runs/{run.run_id}/artifacts/query-answer.md"
    answer = (runtime.data_root / result.answer_path).read_text(encoding="utf-8")
    assert "What says alpha?" in answer
    assert "vault/alpha.md" in answer
    assert result.matched_pages == ["vault/alpha.md"]
    assert result.staged_path is None
    assert result.host_task_path == f"runs/{run.run_id}/host-tasks/query-codex.json"
    assert (runtime.data_root / result.host_task_path).is_file()


def test_query_stage_writes_synthesis_candidate_without_publishing(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root)
    (runtime.vault_dir / "beta.md").write_text(
        "---\npage_type: note\nsources:\n  - raw/source.md\n---\n# Beta\n\nReusable answer material.",
        encoding="utf-8",
    )
    run = RunStore(runtime.runs_dir).start("query", "codex")

    result = query_vault(
        runtime=runtime,
        question="beta reusable",
        run_id=run.run_id,
        host="codex",
        stage=True,
    )

    assert result.staged_path == "staging/synthesis/beta-reusable.md"
    staged = (runtime.data_root / result.staged_path).read_text(encoding="utf-8")
    assert "page_type: synthesis" in staged
    assert "status: staged" in staged
    assert "question: beta reusable" in staged
    assert "sources:\n  - vault/beta.md" in staged
    assert not (runtime.vault_dir / "synthesis" / "beta-reusable.md").exists()

    state = ProjectState.load(runtime.state_dir)
    synthesis = state.syntheses()["synthesis:beta-reusable"]
    assert synthesis["question"] == "beta reusable"
    assert synthesis["sources"] == ["vault/beta.md"]
    assert synthesis["staged_path"] == "staging/synthesis/beta-reusable.md"
    page = state.get_page("staging/synthesis/beta-reusable.md")
    assert page.page_type == "synthesis"


def test_query_stage_without_matches_remains_run_artifact_only(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root)
    run = RunStore(runtime.runs_dir).start("query", "codex")

    result = query_vault(
        runtime=runtime,
        question="missing topic",
        run_id=run.run_id,
        host="codex",
        stage=True,
    )

    assert result.staged_path is None
    assert result.answer_path == f"runs/{run.run_id}/artifacts/query-answer.md"
    assert not (runtime.staging_dir / "synthesis").exists()
    assert ProjectState.load(runtime.state_dir).syntheses() == {}
