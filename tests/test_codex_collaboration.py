from __future__ import annotations

import json
from pathlib import Path

import pytest

from tellme.codex import CodexResultError, consume_codex_result, create_codex_handoff
from tellme.config import load_runtime
from tellme.ingest import ingest_file
from tellme.project import init_project
from tellme.runs import RunStore
from tellme.state import ContentStatus, ProjectState


def test_codex_handoff_writes_markdown_task_and_result_template(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nCodex should synthesize this.", encoding="utf-8")
    runs = RunStore(runtime.runs_dir)
    ingest_run = runs.start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    handoff_run = runs.start("compile", "codex")

    result = create_codex_handoff(runtime=runtime, run_id=handoff_run.run_id)

    task_markdown = (runtime.data_root / result.task_markdown_path).read_text(encoding="utf-8")
    assert result.task_json_path == f"runs/{handoff_run.run_id}/host-tasks/compile-codex.json"
    assert result.task_markdown_path == f"runs/{handoff_run.run_id}/host-tasks/compile-codex.md"
    assert result.result_template_path == f"runs/{handoff_run.run_id}/artifacts/codex-result.template.json"
    assert "TellMe Codex Compile Task" in task_markdown
    assert "Produce a structured knowledge graph update candidate" in task_markdown
    assert "concepts, claims, relations, and conflicts" in task_markdown
    assert "raw/source.md" in task_markdown
    assert "Do not modify `raw/`" in task_markdown
    assert "This handoff is for extraction and graph alignment" in task_markdown
    assert "Do not try to write the final reader-facing article" in task_markdown
    assert "`theme` and `subtheme`" in task_markdown
    assert "`reader_role`" in task_markdown

    template = json.loads((runtime.data_root / result.result_template_path).read_text(encoding="utf-8"))
    assert template["schema_version"] == 1
    assert template["host"] == "codex"
    assert template["run_id"] == handoff_run.run_id
    assert template["output_path"].startswith("staging/graph/candidates/")
    assert template["source_references"] == ["raw/source.md"]
    assert template["graph_candidate"]["candidate_type"] == "knowledge_graph_update"
    assert template["graph_candidate"]["nodes"] == []


def test_codex_handoff_includes_existing_graph_nodes(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    state = ProjectState.load(runtime.state_dir)
    state.upsert_node(
        {
            "id": "concept:existing-node",
            "kind": "concept",
            "title": "Existing Node",
            "summary": "Already published knowledge point.",
            "sources": ["raw/old.md"],
            "status": "published",
            "published_path": "wiki/concepts/existing-node.md",
        }
    )
    handoff_run = RunStore(runtime.runs_dir).start("compile", "codex")

    result = create_codex_handoff(runtime=runtime, run_id=handoff_run.run_id)

    task_markdown = (runtime.data_root / result.task_markdown_path).read_text(encoding="utf-8")
    assert "## Existing Graph Nodes" in task_markdown
    assert "`concept:existing-node`" in task_markdown
    assert "wiki/concepts/existing-node.md" in task_markdown
    assert "reader-facing publication layer later" in task_markdown


def test_codex_handoff_can_focus_on_health_finding_context(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nHealth finding source.", encoding="utf-8")
    runs = RunStore(runtime.runs_dir)
    ingest_run = runs.start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    state = ProjectState.load(runtime.state_dir)
    state.upsert_health_finding(
        {
            "id": "health:thin-node-needs-enrichment",
            "finding_type": "thin_node",
            "summary": "Thin Node needs more sourced claims.",
            "affected_ids": ["concept:thin-node"],
            "sources": ["raw/source.md"],
            "recommendation": "Add claims or synthesis that deepen the node.",
            "confidence": "high",
            "suggested_next_action": "enrich_node",
            "status": "staged",
            "staged_path": "staging/health/health-thin-node-needs-enrichment.md",
            "last_host": "codex",
            "last_run_id": "consume-run",
        }
    )
    handoff_run = runs.start("compile", "codex")

    result = create_codex_handoff(
        runtime=runtime,
        run_id=handoff_run.run_id,
        health_finding_id="health:thin-node-needs-enrichment",
    )

    task_markdown = (runtime.data_root / result.task_markdown_path).read_text(encoding="utf-8")
    assert "## Health Finding Focus" in task_markdown
    assert "Thin Node needs more sourced claims." in task_markdown
    assert "suggested_next_action: enrich_node" in task_markdown
    template = json.loads((runtime.data_root / result.result_template_path).read_text(encoding="utf-8"))
    assert template["source_references"] == ["raw/source.md"]


def test_consume_codex_result_registers_staged_page(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    staged_page = runtime.staging_dir / "codex" / "answer.md"
    staged_page.parent.mkdir(parents=True)
    staged_page.write_text(
        "---\npage_type: synthesis\nsources:\n  - raw/source.md\n---\n# Answer\n\nCodex draft.",
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/codex/answer.md",
                "source_references": ["raw/source.md"],
                "confidence": "review-required",
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    result = consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    assert result.staged_page == "staging/codex/answer.md"
    page = ProjectState.load(runtime.state_dir).get_page("staging/codex/answer.md")
    assert page.status == ContentStatus.STAGED
    assert page.sources == ["raw/source.md"]
    assert page.last_host == "codex"
    assert page.last_run_id == "consume-run"


def test_consume_codex_result_rejects_output_outside_staging(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    result_path = runtime.runs_dir / "bad-result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "wiki/unsafe.md",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexResultError):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")
