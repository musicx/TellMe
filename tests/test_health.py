from __future__ import annotations

import json
from pathlib import Path

import pytest

from tellme.config import load_runtime
from tellme.health import (
    HealthResultError,
    consume_health_result,
    create_health_handoff,
    resolve_health_finding,
)
from tellme.ingest import ingest_file
from tellme.project import init_project
from tellme.runs import RunStore
from tellme.state import ProjectState


def test_create_health_handoff_writes_task_and_result_template(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    state = ProjectState.load(runtime.state_dir)
    state.upsert_node(
        {
            "id": "concept:thin-node",
            "kind": "concept",
            "title": "Thin Node",
            "status": "published",
            "sources": ["raw/source.md"],
            "published_path": "vault/concepts/thin-node.md",
        }
    )
    state.upsert_conflict(
        {
            "id": "conflict:needs-review",
            "summary": "Needs review",
            "status": "staged",
            "sources": ["raw/source.md"],
            "staged_path": "staging/conflicts/needs-review.md",
        }
    )
    state.upsert_relation(
        {
            "id": "concept:thin-node->supports->concept:missing",
            "source": "concept:thin-node",
            "target": "concept:missing",
            "type": "supports",
            "status": "staged",
            "sources": ["raw/source.md"],
        }
    )

    result = create_health_handoff(runtime=runtime, run_id="health-run", host="codex")

    assert result.task_json_path == "runs/health-run/host-tasks/health-codex.json"
    assert result.task_markdown_path == "runs/health-run/host-tasks/health-codex.md"
    assert result.result_template_path == "runs/health-run/artifacts/health-result.template.json"
    task_markdown = (runtime.data_root / result.task_markdown_path).read_text(encoding="utf-8")
    assert "TellMe Health Reflection Task" in task_markdown
    assert "`concept:thin-node`" in task_markdown
    assert "conflict:needs-review" in task_markdown
    assert "concept:missing" in task_markdown
    assert "thin_node" in task_markdown

    template = json.loads((runtime.data_root / result.result_template_path).read_text(encoding="utf-8"))
    assert template["schema_version"] == 1
    assert template["candidate_type"] == "health_findings"
    assert template["output_path"] == "staging/health/health-run.json"
    assert template["health_findings"] == []


def test_consume_health_result_registers_findings_and_review_pages(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nThin node evidence.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    state = ProjectState.load(runtime.state_dir)
    state.upsert_node(
        {
            "id": "concept:thin-node",
            "kind": "concept",
            "title": "Thin Node",
            "status": "published",
            "sources": ["raw/source.md"],
            "published_path": "vault/concepts/thin-node.md",
        }
    )
    result_path = runtime.staging_dir / "health" / "health-run.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "health_findings",
                "run_id": "health-run",
                "host": "codex",
                "output_path": "staging/health/health-run.json",
                "health_findings": [
                    {
                        "id": "health:thin-node-needs-enrichment",
                        "finding_type": "thin_node",
                        "summary": "Thin Node needs more sourced claims.",
                        "affected_ids": ["concept:thin-node"],
                        "sources": ["raw/source.md"],
                        "recommendation": "Add claims or synthesis that deepen the node.",
                        "confidence": "high",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = consume_health_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    assert result.result_path == "staging/health/health-run.json"
    assert result.staged_pages == ["staging/health/health-thin-node-needs-enrichment.md"]
    page_text = (runtime.staging_dir / "health" / "health-thin-node-needs-enrichment.md").read_text(encoding="utf-8")
    assert "page_type: health_finding" in page_text
    assert "finding_type: thin_node" in page_text
    assert "suggested_next_action: enrich_node" in page_text
    assert "Thin Node needs more sourced claims." in page_text

    finding = ProjectState.load(runtime.state_dir).health_findings()["health:thin-node-needs-enrichment"]
    assert finding["status"] == "staged"
    assert finding["suggested_next_action"] == "enrich_node"
    assert finding["staged_path"] == "staging/health/health-thin-node-needs-enrichment.md"
    assert finding["last_run_id"] == "consume-run"


def test_consume_health_result_rejects_unregistered_sources(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    result_path = runtime.staging_dir / "health" / "health-run.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "health_findings",
                "run_id": "health-run",
                "host": "codex",
                "output_path": "staging/health/health-run.json",
                "health_findings": [
                    {
                        "id": "health:missing-source",
                        "finding_type": "thin_node",
                        "summary": "Unsourced finding.",
                        "affected_ids": ["concept:missing"],
                        "sources": ["raw/missing.md"],
                        "recommendation": "Review the missing source.",
                        "confidence": "medium",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HealthResultError, match="registered sources"):
        consume_health_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")


def test_resolve_health_finding_marks_finding_resolved(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    state = ProjectState.load(runtime.state_dir)
    review_page = runtime.staging_dir / "health" / "health-thin-node-needs-enrichment.md"
    review_page.parent.mkdir(parents=True)
    review_page.write_text(
        "---\npage_type: health_finding\nstatus: staged\nfinding_id: health:thin-node-needs-enrichment\n---\n# Finding\n",
        encoding="utf-8",
    )
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

    result = resolve_health_finding(
        runtime=runtime,
        finding_id="health:thin-node-needs-enrichment",
        host="codex",
        run_id="resolve-run",
    )

    assert result.finding_id == "health:thin-node-needs-enrichment"
    finding = ProjectState.load(runtime.state_dir).health_findings()["health:thin-node-needs-enrichment"]
    assert finding["status"] == "resolved"
    assert finding["last_run_id"] == "resolve-run"
    page_text = review_page.read_text(encoding="utf-8")
    assert "status: resolved" in page_text
