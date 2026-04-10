from __future__ import annotations

import json
from pathlib import Path

from tellme.config import load_runtime
from tellme.health import create_health_handoff
from tellme.project import init_project
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
