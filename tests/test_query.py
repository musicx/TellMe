from __future__ import annotations

from pathlib import Path

from tellme.config import load_runtime
from tellme.project import init_project
from tellme.query import query_vault
from tellme.runs import RunStore


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


def test_query_stage_writes_reviewable_candidate_without_publishing(tmp_path: Path) -> None:
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

    assert result.staged_path == "staging/queries/beta-reusable.md"
    staged = (runtime.data_root / result.staged_path).read_text(encoding="utf-8")
    assert "page_type: query_answer" in staged
    assert "status: staged" in staged
    assert not (runtime.vault_dir / "queries" / "beta-reusable.md").exists()
