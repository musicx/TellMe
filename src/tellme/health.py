from __future__ import annotations

from dataclasses import dataclass

from .config import ProjectRuntime
from .files import atomic_write_json
from .hosts import HostTask
from .state import ContentStatus, ProjectState


@dataclass(frozen=True)
class HealthHandoffResult:
    task_json_path: str
    task_markdown_path: str
    result_template_path: str


def create_health_handoff(runtime: ProjectRuntime, run_id: str, host: str) -> HealthHandoffResult:
    state = ProjectState.load(runtime.state_dir)
    summary = _health_summary(state)
    task = HostTask(
        command="health",
        run_id=run_id,
        host=host,
        allowed_read_roots=["state", "vault", "staging"],
        allowed_write_roots=["staging", "runs"],
        inputs=[],
        expected_output=f"staging/health/{run_id}.json",
    )
    task_json = task.write(runtime.runs_dir / run_id / "host-tasks")
    task_markdown = task_json.with_suffix(".md")
    task_markdown.write_text(_task_markdown(task=task, summary=summary), encoding="utf-8")

    result_template = runtime.runs_dir / run_id / "artifacts" / "health-result.template.json"
    atomic_write_json(
        result_template,
        {
            "schema_version": 1,
            "candidate_type": "health_findings",
            "run_id": run_id,
            "host": host,
            "output_path": f"staging/health/{run_id}.json",
            "health_findings": [],
        },
    )
    return HealthHandoffResult(
        task_json_path=_relative(runtime.data_root, task_json),
        task_markdown_path=_relative(runtime.data_root, task_markdown),
        result_template_path=_relative(runtime.data_root, result_template),
    )


def _health_summary(state: ProjectState) -> dict[str, list[str]]:
    node_ids = set(state.nodes())
    claim_subjects = {str(claim.get("subject")) for claim in state.claims().values()}
    thin_nodes = [
        node_id
        for node_id, node in state.nodes().items()
        if node.get("status") == ContentStatus.PUBLISHED.value and node_id not in claim_subjects
    ]
    unresolved_conflicts = [
        str(conflict_id)
        for conflict_id, conflict in state.conflicts().items()
        if conflict.get("status") != ContentStatus.PUBLISHED.value and conflict.get("status") != "resolved"
    ]
    orphan_relations: list[str] = []
    for relation_id, relation in state.relations().items():
        source = str(relation.get("source", ""))
        target = str(relation.get("target", ""))
        if source and source not in node_ids:
            orphan_relations.append(f"{relation_id}: missing source {source}")
        if target and target not in node_ids:
            orphan_relations.append(f"{relation_id}: missing target {target}")
    return {
        "nodes": sorted(node_ids),
        "thin_nodes": sorted(thin_nodes),
        "unresolved_conflicts": sorted(unresolved_conflicts),
        "orphan_relations": sorted(orphan_relations),
    }


def _task_markdown(task: HostTask, summary: dict[str, list[str]]) -> str:
    return f"""# TellMe Health Reflection Task

Run id: `{task.run_id}`
Host: `{task.host}`

## Goal

Review the TellMe wiki graph for missing knowledge, weak links, contradictions, duplicate concepts, thin nodes, and useful new article candidates. Write health findings to `{task.expected_output}` and keep all generated material under `staging/` or `runs/`.

## Existing Graph Nodes

{_bullet_list(summary["nodes"], empty="No graph nodes.")}

## Thin Nodes

Use finding type `thin_node` for nodes that need stronger claims, evidence, or synthesis.

{_bullet_list(summary["thin_nodes"], empty="No thin nodes detected deterministically.")}

## Unresolved Conflicts

{_bullet_list(summary["unresolved_conflicts"], empty="No unresolved conflicts.")}

## Orphan Relations

{_bullet_list(summary["orphan_relations"], empty="No orphan relations detected.")}

## Required Health Finding Schema

Each finding should include:

- `id`
- `finding_type`
- `summary`
- `affected_ids`
- `sources`
- `recommendation`
- `confidence`

Do not modify `raw/`.
Do not publish directly to `vault/`.
"""


def _bullet_list(items: list[str], empty: str) -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- `{item}`" for item in items)


def _relative(root, path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
