from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectRuntime
from .files import atomic_write_json
from .hosts import KNOWN_HOSTS, HostTask
from .state import ContentStatus, PageRecord, ProjectState


class HealthResultError(RuntimeError):
    """Raised when a health reflection result cannot be safely consumed."""


@dataclass(frozen=True)
class HealthHandoffResult:
    task_json_path: str
    task_markdown_path: str
    result_template_path: str


@dataclass(frozen=True)
class HealthConsumeResult:
    result_path: str
    finding_ids: list[str]
    staged_pages: list[str]


@dataclass(frozen=True)
class HealthResolveResult:
    finding_id: str


def create_health_handoff(runtime: ProjectRuntime, run_id: str, host: str) -> HealthHandoffResult:
    state = ProjectState.load(runtime.state_dir)
    summary = _health_summary(state)
    task = HostTask(
        command="health",
        run_id=run_id,
        host=host,
        allowed_read_roots=["state", "wiki", "staging"],
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


def consume_health_result(
    runtime: ProjectRuntime,
    result_path: Path,
    consume_run_id: str,
) -> HealthConsumeResult:
    resolved_path = result_path.resolve()
    try:
        resolved_path.relative_to(runtime.staging_dir.resolve())
    except ValueError as exc:
        raise HealthResultError("health result path must be under staging/") from exc
    if not resolved_path.is_file():
        raise HealthResultError(f"health result file not found: {_relative(runtime.data_root, resolved_path)}")

    payload = _load_health_result(resolved_path)
    rel_result_path = _relative(runtime.data_root, resolved_path)
    if not rel_result_path.startswith("staging/health/"):
        raise HealthResultError("health result path must be under staging/health/")
    if str(payload["output_path"]) != rel_result_path:
        raise HealthResultError("health result output_path must match the consumed file path")

    state = ProjectState.load(runtime.state_dir)
    known_sources = set(state.sources())
    finding_ids: list[str] = []
    staged_pages: list[str] = []
    host = str(payload["host"])

    for finding in payload["health_findings"]:
        sources = _require_string_list(finding, "sources", f"finding {finding['id']}")
        unknown_sources = sorted(set(sources) - known_sources)
        if unknown_sources:
            raise HealthResultError(f"health finding references sources not registered sources: {unknown_sources}")

        affected_ids = _require_string_list(finding, "affected_ids", f"finding {finding['id']}")
        finding_id = str(finding["id"])
        suggested_next_action = _suggested_next_action(str(finding["finding_type"]))
        page_path = runtime.staging_dir / "health" / f"{_slug(finding_id)}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            _health_finding_page(
                finding=finding,
                suggested_next_action=suggested_next_action,
                host=host,
                run_id=consume_run_id,
            ),
            encoding="utf-8",
        )
        rel_page_path = _relative(runtime.data_root, page_path)
        state.upsert_page(
            PageRecord(
                path=rel_page_path,
                page_type="health_finding",
                status=ContentStatus.STAGED,
                sha256=hashlib.sha256(page_path.read_bytes()).hexdigest(),
                sources=sources,
                last_host=host,
                last_run_id=consume_run_id,
                staged_path=rel_page_path,
            )
        )
        state.upsert_health_finding(
            {
                "id": finding_id,
                "finding_type": str(finding["finding_type"]),
                "summary": str(finding["summary"]),
                "affected_ids": affected_ids,
                "sources": sources,
                "recommendation": str(finding["recommendation"]),
                "confidence": str(finding["confidence"]),
                "suggested_next_action": suggested_next_action,
                "status": ContentStatus.STAGED.value,
                "staged_path": rel_page_path,
                "result_path": rel_result_path,
                "last_host": host,
                "last_run_id": consume_run_id,
            }
        )
        finding_ids.append(finding_id)
        staged_pages.append(rel_page_path)

    return HealthConsumeResult(
        result_path=rel_result_path,
        finding_ids=finding_ids,
        staged_pages=staged_pages,
    )


def resolve_health_finding(
    runtime: ProjectRuntime,
    finding_id: str,
    host: str,
    run_id: str,
) -> HealthResolveResult:
    state = ProjectState.load(runtime.state_dir)
    finding = state.health_findings().get(finding_id)
    if not finding:
        raise HealthResultError(f"unknown health finding: {finding_id}")
    updated = dict(finding)
    updated["status"] = "resolved"
    updated["last_host"] = host
    updated["last_run_id"] = run_id
    state.upsert_health_finding(updated)

    staged_path = str(finding.get("staged_path", ""))
    if staged_path:
        page_path = runtime.data_root / staged_path
        if page_path.is_file():
            page_path.write_text(
                _replace_frontmatter_scalar(
                    _replace_frontmatter_scalar(
                        _replace_frontmatter_scalar(
                            page_path.read_text(encoding="utf-8"),
                            "status",
                            "resolved",
                        ),
                        "last_host",
                        host,
                    ),
                    "last_run_id",
                    run_id,
                ),
                encoding="utf-8",
            )
            page_record = state.pages().get(staged_path)
            if page_record:
                state.upsert_page(
                    PageRecord(
                        path=staged_path,
                        page_type=str(page_record["page_type"]),
                        status=ContentStatus.RECONCILED,
                        sha256=hashlib.sha256(page_path.read_bytes()).hexdigest(),
                        sources=list(page_record.get("sources", [])),
                        last_host=host,
                        last_run_id=run_id,
                        staged_path=staged_path,
                    )
                )

    return HealthResolveResult(finding_id=finding_id)


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

Also review the published wiki as a reading surface. Look for readability and reader guidance issues, not only graph coverage issues.

## Existing Graph Nodes

{_bullet_list(summary["nodes"], empty="No graph nodes.")}

## Thin Nodes

Use finding type `thin_node` for nodes that need stronger claims, evidence, or synthesis.

{_bullet_list(summary["thin_nodes"], empty="No thin nodes detected deterministically.")}

## Unresolved Conflicts

{_bullet_list(summary["unresolved_conflicts"], empty="No unresolved conflicts.")}

## Orphan Relations

{_bullet_list(summary["orphan_relations"], empty="No orphan relations detected.")}

## Reader-Facing Readability Review

Audit published `overview`, `theme`, `subtheme`, and `reference` pages for:

- weak or generic summaries
- pages that open with metadata or claim dumps instead of orientation
- themes that list nodes but do not provide a reading path
- references that feel like extracted cards instead of precise definitions
- pages where evidence overwhelms explanation

Use these finding types when relevant:

- `weak_summary`
- `missing_orientation`
- `theme_needs_reading_path`
- `reference_too_card_like`
- `evidence_overwhelms_explanation`

## Required Health Finding Schema

Each finding should include:

- `id`
- `finding_type`
- `summary`
- `affected_ids`
- `sources`
- `recommendation`
- `confidence`

Recommendations should say how the page should be rewritten or reorganized, not only that it is weak.

Do not modify `raw/`.
Do not publish directly to `wiki/`.
"""


def _load_health_result(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HealthResultError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise HealthResultError("health result must be a JSON object")
    if int(payload.get("schema_version", 0)) != 1:
        raise HealthResultError("unsupported health result schema_version")
    if payload.get("candidate_type") != "health_findings":
        raise HealthResultError("candidate_type must be health_findings")
    host = str(payload.get("host", ""))
    if host not in KNOWN_HOSTS:
        raise HealthResultError(f"unknown host: {host}")
    for field in ("run_id", "output_path"):
        if not str(payload.get(field, "")).strip():
            raise HealthResultError(f"health result missing {field}")
    findings = payload.get("health_findings")
    if not isinstance(findings, list):
        raise HealthResultError("health_findings must be a list")
    for finding in findings:
        if not isinstance(finding, dict):
            raise HealthResultError("health_findings must contain objects")
        for field in ("id", "finding_type", "summary", "recommendation", "confidence"):
            if not str(finding.get(field, "")).strip():
                raise HealthResultError(f"health finding missing {field}")
        _require_string_list(finding, "affected_ids", f"finding {finding.get('id', '<unknown>')}")
        _require_string_list(finding, "sources", f"finding {finding.get('id', '<unknown>')}")
    return payload


def _require_string_list(payload: dict, field: str, label: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise HealthResultError(f"{label} must include {field}")
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        raise HealthResultError(f"{label} must include {field}")
    return items


def _health_finding_page(
    finding: dict,
    suggested_next_action: str,
    host: str,
    run_id: str,
) -> str:
    now = _utc_now()
    sources = _require_string_list(finding, "sources", f"finding {finding['id']}")
    affected_ids = _require_string_list(finding, "affected_ids", f"finding {finding['id']}")
    source_lines = "\n".join(f"- `{source}`" for source in sources)
    affected_lines = "\n".join(f"- `{affected_id}`" for affected_id in affected_ids)
    return (
        "---\n"
        "page_type: health_finding\n"
        "status: staged\n"
        f"finding_id: {finding['id']}\n"
        f"finding_type: {finding['finding_type']}\n"
        f"suggested_next_action: {suggested_next_action}\n"
        f"confidence: {finding['confidence']}\n"
        f"affected_ids: [{', '.join(affected_ids)}]\n"
        f"sources: [{', '.join(sources)}]\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"last_host: {host}\n"
        f"last_run_id: {run_id}\n"
        "---\n"
        f"# {finding['summary']}\n\n"
        "## Recommendation\n\n"
        f"{finding['recommendation']}\n\n"
        "## Affected Records\n\n"
        f"{affected_lines}\n\n"
        "## Evidence Sources\n\n"
        f"{source_lines}\n"
    )


def _suggested_next_action(finding_type: str) -> str:
    return {
        "thin_node": "enrich_node",
        "missing_node": "create_node_candidate",
        "weak_link": "propose_relation",
        "duplicate_concept": "review_duplicate",
        "conflict_followup": "review_conflict",
        "weak_summary": "rewrite_page_summary",
        "missing_orientation": "reader_rewrite",
        "theme_needs_reading_path": "reader_rewrite",
        "reference_too_card_like": "reader_rewrite",
        "evidence_overwhelms_explanation": "reader_rewrite",
    }.get(finding_type, "manual_review")


def _replace_frontmatter_scalar(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^({re.escape(key)}:\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(rf"\g<1>{value}", text, count=1)
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end == -1:
        return text
    return text[:end] + f"\n{key}: {value}" + text[end:]


def _bullet_list(items: list[str], empty: str) -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- `{item}`" for item in items)


def _relative(root, path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "health-finding"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
