from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ProjectRuntime
from .state import ContentStatus, PageRecord, ProjectState


class GraphCandidateError(RuntimeError):
    """Raised when a graph candidate cannot be safely staged."""


@dataclass(frozen=True)
class GraphStageResult:
    staged_pages: list[str]
    nodes: list[str]
    claims: list[str]
    relations: list[str]
    conflicts: list[str]


def stage_graph_candidate(
    runtime: ProjectRuntime,
    candidate_path: Path,
    host: str,
    run_id: str,
    expected_source_references: list[str] | None = None,
) -> GraphStageResult:
    candidate = _load_candidate(candidate_path)
    _validate_candidate(candidate, expected_source_references=expected_source_references)

    state = ProjectState.load(runtime.state_dir)
    known_sources = set(state.sources())
    unknown_sources = sorted(set(candidate["source_references"]) - known_sources)
    if unknown_sources:
        raise GraphCandidateError(f"graph candidate references sources not registered sources: {unknown_sources}")

    staged_pages: list[str] = []
    staged_nodes: list[str] = []
    staged_claims: list[str] = []
    staged_relations: list[str] = []
    staged_conflicts: list[str] = []
    nodes_by_id = {str(node["id"]): node for node in candidate["nodes"]}

    for node in candidate["nodes"]:
        node_id = str(node["id"])
        kind = str(node["kind"])
        slug = _slug(_node_slug_value(node_id=node_id, title=str(node["title"])))
        page_path = runtime.staging_dir / _node_collection(kind) / f"{slug}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            _node_page(
                node=node,
                claims=[claim for claim in candidate["claims"] if claim["subject"] == node_id],
                relations=[relation for relation in candidate["relations"] if relation["source"] == node_id],
                nodes_by_id=nodes_by_id,
                host=host,
                run_id=run_id,
            ),
            encoding="utf-8",
        )
        rel = _relative(runtime.data_root, page_path)
        sources = _as_str_list(node["sources"])
        page_hash = hashlib.sha256(page_path.read_bytes()).hexdigest()
        state.upsert_page(
            PageRecord(
                path=rel,
                page_type=kind,
                status=ContentStatus.STAGED,
                sha256=page_hash,
                sources=sources,
                last_host=host,
                last_run_id=run_id,
                staged_path=rel,
            )
        )
        node_record = dict(node)
        node_record["status"] = ContentStatus.STAGED.value
        node_record["staged_path"] = rel
        node_record["last_host"] = host
        node_record["last_run_id"] = run_id
        state.upsert_node(node_record)
        staged_pages.append(rel)
        staged_nodes.append(node_id)

    for claim in candidate["claims"]:
        claim_record = dict(claim)
        claim_record["status"] = ContentStatus.STAGED.value
        claim_record["last_host"] = host
        claim_record["last_run_id"] = run_id
        state.upsert_claim(claim_record)
        staged_claims.append(str(claim["id"]))

    for relation in candidate["relations"]:
        relation_record = dict(relation)
        relation_record["id"] = _relation_id(relation)
        relation_record["status"] = ContentStatus.STAGED.value
        relation_record["last_host"] = host
        relation_record["last_run_id"] = run_id
        state.upsert_relation(relation_record)
        staged_relations.append(str(relation_record["id"]))

    for conflict in candidate["conflicts"]:
        conflict_id = str(conflict["id"])
        page_path = runtime.staging_dir / "conflicts" / f"{_slug(_node_slug_value(conflict_id, conflict_id))}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            _conflict_page(conflict=conflict, host=host, run_id=run_id),
            encoding="utf-8",
        )
        rel = _relative(runtime.data_root, page_path)
        sources = _as_str_list(conflict["sources"])
        page_hash = hashlib.sha256(page_path.read_bytes()).hexdigest()
        state.upsert_page(
            PageRecord(
                path=rel,
                page_type="conflict",
                status=ContentStatus.STAGED,
                sha256=page_hash,
                sources=sources,
                last_host=host,
                last_run_id=run_id,
                staged_path=rel,
            )
        )
        conflict_record = dict(conflict)
        conflict_record["status"] = ContentStatus.STAGED.value
        conflict_record["staged_path"] = rel
        conflict_record["last_host"] = host
        conflict_record["last_run_id"] = run_id
        state.upsert_conflict(conflict_record)
        staged_pages.append(rel)
        staged_conflicts.append(conflict_id)

    return GraphStageResult(
        staged_pages=staged_pages,
        nodes=staged_nodes,
        claims=staged_claims,
        relations=staged_relations,
        conflicts=staged_conflicts,
    )


def is_graph_candidate_path(path: Path) -> bool:
    return path.suffix.lower() == ".json" and "graph" in {part.lower() for part in path.parts}


def _load_candidate(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise GraphCandidateError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise GraphCandidateError("graph candidate must be a JSON object")
    return payload


def _validate_candidate(
    candidate: dict[str, Any],
    expected_source_references: list[str] | None = None,
) -> None:
    if int(candidate.get("schema_version", 0)) != 1:
        raise GraphCandidateError("unsupported graph candidate schema_version")
    if candidate.get("candidate_type") != "knowledge_graph_update":
        raise GraphCandidateError("candidate_type must be knowledge_graph_update")
    source_references = _require_sources(candidate, "source_references", "candidate")
    if expected_source_references is not None:
        expected_sources = set(expected_source_references)
        unknown_sources = sorted(source_references - expected_sources)
        if unknown_sources:
            raise GraphCandidateError(f"candidate source_references outside host result: {unknown_sources}")
    for field in ("nodes", "claims", "relations", "conflicts"):
        value = candidate.get(field)
        if not isinstance(value, list):
            raise GraphCandidateError(f"{field} must be a list")

    node_ids: set[str] = set()
    for node in candidate["nodes"]:
        if not isinstance(node, dict):
            raise GraphCandidateError("nodes must contain objects")
        for field in ("id", "kind", "title", "summary"):
            if not str(node.get(field, "")).strip():
                raise GraphCandidateError(f"node missing {field}")
        if node["kind"] not in {"concept", "entity"}:
            raise GraphCandidateError("node kind must be concept or entity")
        _require_sources(node, "sources", f"node {node['id']}", source_references)
        node_ids.add(str(node["id"]))

    for claim in candidate["claims"]:
        if not isinstance(claim, dict):
            raise GraphCandidateError("claims must contain objects")
        for field in ("id", "subject", "text"):
            if not str(claim.get(field, "")).strip():
                raise GraphCandidateError(f"claim missing {field}")
        if str(claim["subject"]) not in node_ids:
            raise GraphCandidateError(f"claim subject does not match candidate node: {claim['subject']}")
        _require_sources(claim, "sources", f"claim {claim['id']}", source_references)

    for relation in candidate["relations"]:
        if not isinstance(relation, dict):
            raise GraphCandidateError("relations must contain objects")
        for field in ("source", "target", "type"):
            if not str(relation.get(field, "")).strip():
                raise GraphCandidateError(f"relation missing {field}")
        if str(relation["source"]) not in node_ids:
            raise GraphCandidateError(f"relation source does not match candidate node: {relation['source']}")
        _require_sources(relation, "sources", f"relation {_relation_id(relation)}", source_references)

    for conflict in candidate["conflicts"]:
        if not isinstance(conflict, dict):
            raise GraphCandidateError("conflicts must contain objects")
        for field in ("id", "summary"):
            if not str(conflict.get(field, "")).strip():
                raise GraphCandidateError(f"conflict missing {field}")
        _require_sources(conflict, "sources", f"conflict {conflict['id']}", source_references)


def _require_sources(
    payload: dict[str, Any],
    field: str,
    label: str,
    allowed: set[str] | None = None,
) -> set[str]:
    sources = set(_as_str_list(payload.get(field)))
    if not sources:
        raise GraphCandidateError(f"{label} must include {field}")
    if allowed is not None:
        unknown = sorted(sources - allowed)
        if unknown:
            raise GraphCandidateError(f"{label} has sources outside source_references: {unknown}")
    return sources


def _node_page(
    node: dict[str, Any],
    claims: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    host: str,
    run_id: str,
) -> str:
    now = _utc_now()
    sources = _as_str_list(node["sources"])
    source_lines = "\n".join(f"  - {source}" for source in sources)
    claim_lines = "\n".join(f"- {claim['text']} [source: {', '.join(_as_str_list(claim['sources']))}]" for claim in claims)
    relation_lines = "\n".join(
        f"- {relation['type']} [[{_relation_target_title(relation, nodes_by_id)}]]"
        f" [source: {', '.join(_as_str_list(relation['sources']))}]"
        for relation in relations
    )
    evidence_lines = "\n".join(f"- `{source}`" for source in sources)
    return (
        "---\n"
        f"page_type: {node['kind']}\n"
        "status: staged\n"
        f"node_id: {node['id']}\n"
        f"node_kind: {node['kind']}\n"
        "sources:\n"
        f"{source_lines}\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"last_host: {host}\n"
        f"last_run_id: {run_id}\n"
        "---\n"
        f"# {node['title']}\n\n"
        f"{node['summary']}\n\n"
        "## Claims\n\n"
        f"{claim_lines or '- No claims staged yet.'}\n\n"
        "## Relations\n\n"
        f"{relation_lines or '- No relations staged yet.'}\n\n"
        "## Evidence\n\n"
        f"{evidence_lines}\n"
    )


def _conflict_page(conflict: dict[str, Any], host: str, run_id: str) -> str:
    now = _utc_now()
    sources = _as_str_list(conflict["sources"])
    source_lines = "\n".join(f"  - {source}" for source in sources)
    evidence_lines = "\n".join(f"- `{source}`" for source in sources)
    claim_lines = "\n".join(f"- `{claim_id}`" for claim_id in _as_str_list(conflict.get("claim_ids")))
    explanation = str(conflict.get("explanation", "No explanation candidate provided."))
    return (
        "---\n"
        "page_type: conflict\n"
        "status: staged\n"
        f"conflict_id: {conflict['id']}\n"
        "sources:\n"
        f"{source_lines}\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"last_host: {host}\n"
        f"last_run_id: {run_id}\n"
        "---\n"
        f"# {conflict['id']}\n\n"
        "## Summary\n\n"
        f"{conflict['summary']}\n\n"
        "## Related Claims\n\n"
        f"{claim_lines or '- No claim ids provided.'}\n\n"
        "## Explanation Candidate\n\n"
        f"{explanation}\n\n"
        "## Evidence\n\n"
        f"{evidence_lines}\n"
    )


def _relation_target_title(relation: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]) -> str:
    target = str(relation["target"])
    if target in nodes_by_id:
        return str(nodes_by_id[target]["title"])
    value = target.split(":", 1)[-1]
    words = re.split(r"[-_\s]+", value)
    return " ".join(_title_word(word) for word in words if word)


def _title_word(word: str) -> str:
    lower = word.lower()
    if lower in {"ai", "api", "llm", "mcp", "pc"}:
        return lower.upper()
    return lower.capitalize()


def _relation_id(relation: dict[str, Any]) -> str:
    return f"{relation['source']}->{relation['type']}->{relation['target']}"


def _node_slug_value(node_id: str, title: str) -> str:
    if ":" in node_id:
        return node_id.split(":", 1)[1]
    return title


def _node_collection(kind: str) -> str:
    return "entities" if kind == "entity" else "concepts"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "node"


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
