from __future__ import annotations

import json
from pathlib import Path

import pytest

from tellme.codex import CodexResultError, consume_codex_result
from tellme.graph import normalize_node_id
from tellme.config import load_runtime
from tellme.ingest import ingest_file
from tellme.linting import lint_vault
from tellme.project import init_project
from tellme.runs import RunStore
from tellme.state import ContentStatus, ProjectState


def test_consume_graph_candidate_stages_concept_page_and_records_graph_state(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nCodex harness engineering improves model usage.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)

    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:codex-harness-engineering",
                        "kind": "concept",
                        "title": "Codex Harness Engineering",
                        "summary": "A harness around Codex for repeatable engineering workflows.",
                        "sources": ["raw/source.md"],
                    }
                ],
                "claims": [
                    {
                        "id": "claim:codex-harness-improves-workflows",
                        "subject": "concept:codex-harness-engineering",
                        "text": "Codex harness engineering improves repeatable model-assisted workflows.",
                        "sources": ["raw/source.md"],
                    }
                ],
                "relations": [
                    {
                        "source": "concept:codex-harness-engineering",
                        "target": "concept:llm-wiki",
                        "type": "supports",
                        "sources": ["raw/source.md"],
                    }
                ],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    result = consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    assert result.staged_page == "staging/concepts/codex-harness-engineering.md"
    assert result.staged_pages == ["staging/concepts/codex-harness-engineering.md"]
    staged_page = runtime.staging_dir / "concepts" / "codex-harness-engineering.md"
    assert staged_page.is_file()
    page_text = staged_page.read_text(encoding="utf-8")
    assert "page_type: concept" in page_text
    assert "node_id: concept:codex-harness-engineering" in page_text
    assert "Codex harness engineering improves repeatable model-assisted workflows." in page_text
    assert "[[LLM Wiki]]" in page_text

    state = ProjectState.load(runtime.state_dir)
    page = state.get_page("staging/concepts/codex-harness-engineering.md")
    assert page.status == ContentStatus.STAGED
    assert page.page_type == "concept"
    assert state.nodes()["concept:codex-harness-engineering"]["staged_path"] == (
        "staging/concepts/codex-harness-engineering.md"
    )
    assert state.claims()["claim:codex-harness-improves-workflows"]["subject"] == (
        "concept:codex-harness-engineering"
    )
    assert state.relations()["concept:codex-harness-engineering->supports->concept:llm-wiki"]["type"] == "supports"


def test_consume_graph_candidate_rejects_missing_source_attribution(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": [],
                "nodes": [
                    {
                        "id": "concept:unsourced",
                        "kind": "concept",
                        "title": "Unsourced",
                        "summary": "Missing evidence should be rejected.",
                        "sources": [],
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexResultError, match="source_references"):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")


def test_consume_graph_candidate_rejects_unregistered_source_reference(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/unregistered.md"],
                "nodes": [
                    {
                        "id": "concept:unregistered-source",
                        "kind": "concept",
                        "title": "Unregistered Source",
                        "summary": "This source was not ingested.",
                        "sources": ["raw/unregistered.md"],
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/unregistered.md"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexResultError, match="registered sources"):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")


def test_consume_graph_candidate_stages_entity_under_entities_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nOpenAI appears as an entity.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "entity:openai",
                        "kind": "entity",
                        "title": "OpenAI",
                        "summary": "An AI organization.",
                        "sources": ["raw/source.md"],
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    result = consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    assert result.staged_page == "staging/entities/openai.md"
    assert (runtime.staging_dir / "entities" / "openai.md").is_file()


def test_consume_graph_candidate_preserves_reader_facing_organization_metadata(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nTellMe architecture source.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:tellme-control-plane",
                        "kind": "concept",
                        "title": "TellMe Control Plane",
                        "summary": "Control plane summary.",
                        "sources": ["raw/source.md"],
                        "theme": "Architecture",
                        "subtheme": "Control Plane",
                        "reader_role": "embedded",
                        "promotion_recommendation": "embedded",
                        "promotion_reason": "Useful inside a larger chapter, but too narrow for a standalone reader-facing page.",
                        "standalone_value": "medium",
                        "theme_fit": "high",
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    node = ProjectState.load(runtime.state_dir).nodes()["concept:tellme-control-plane"]
    assert node["theme"] == "Architecture"
    assert node["subtheme"] == "Control Plane"
    assert node["reader_role"] == "embedded"
    assert node["promotion_recommendation"] == "embedded"
    assert node["promotion_reason"].startswith("Useful inside a larger chapter")
    assert node["standalone_value"] == "medium"
    assert node["theme_fit"] == "high"


def test_consume_graph_candidate_rejects_invalid_promotion_recommendation(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nPromotion validation.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:bad-promotion",
                        "kind": "concept",
                        "title": "Bad Promotion",
                        "summary": "Invalid promotion metadata.",
                        "sources": ["raw/source.md"],
                        "promotion_recommendation": "unknown",
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexResultError, match="promotion_recommendation"):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")


def test_consume_graph_candidate_stages_conflict_page(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nThe article contains a tension worth reviewing.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:codex-graph-candidate",
                        "kind": "concept",
                        "title": "Codex Graph Candidate",
                        "summary": "Structured candidate output from Codex.",
                        "sources": ["raw/source.md"],
                    }
                ],
                "claims": [
                    {
                        "id": "claim:one",
                        "subject": "concept:codex-graph-candidate",
                        "text": "One claim.",
                        "sources": ["raw/source.md"],
                    },
                    {
                        "id": "claim:two",
                        "subject": "concept:codex-graph-candidate",
                        "text": "A tensioned claim.",
                        "sources": ["raw/source.md"],
                    },
                ],
                "relations": [],
                "conflicts": [
                    {
                        "id": "conflict:codex-candidate-tension",
                        "summary": "The two claims require human review.",
                        "claim_ids": ["claim:one", "claim:two"],
                        "explanation": "They may describe different scopes rather than a hard contradiction.",
                        "sources": ["raw/source.md"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    result = consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    assert "staging/conflicts/codex-candidate-tension.md" in result.staged_pages
    conflict_page = runtime.staging_dir / "conflicts" / "codex-candidate-tension.md"
    assert conflict_page.is_file()
    conflict_text = conflict_page.read_text(encoding="utf-8")
    assert "page_type: conflict" in conflict_text
    assert "conflict_id: conflict:codex-candidate-tension" in conflict_text
    assert "They may describe different scopes rather than a hard contradiction." in conflict_text
    state = ProjectState.load(runtime.state_dir)
    assert state.get_page("staging/conflicts/codex-candidate-tension.md").page_type == "conflict"
    assert state.conflicts()["conflict:codex-candidate-tension"]["staged_path"] == (
        "staging/conflicts/codex-candidate-tension.md"
    )


def test_consume_graph_candidate_marks_existing_node_as_enrichment(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    state = ProjectState.load(runtime.state_dir)
    state.upsert_node(
        {
            "id": "concept:codex-graph-candidate",
            "kind": "concept",
            "title": "Codex Graph Candidate",
            "summary": "Existing published node.",
            "sources": ["raw/old.md"],
            "status": "published",
            "published_path": "wiki/concepts/codex-graph-candidate.md",
        }
    )
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nNew evidence enriches an existing node.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    candidate_path = runtime.staging_dir / "graph" / "candidates" / "candidate.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:codex-graph-candidate",
                        "kind": "concept",
                        "title": "Codex Graph Candidate",
                        "summary": "New evidence enriches this node.",
                        "sources": ["raw/source.md"],
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/graph/candidates/candidate.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    page_text = (runtime.staging_dir / "concepts" / "codex-graph-candidate.md").read_text(encoding="utf-8")
    assert "update_action: enrich_existing" in page_text
    assert "previous_published_path: wiki/concepts/codex-graph-candidate.md" in page_text
    node = ProjectState.load(runtime.state_dir).nodes()["concept:codex-graph-candidate"]
    assert node["update_action"] == "enrich_existing"
    assert node["previous_published_path"] == "wiki/concepts/codex-graph-candidate.md"


def test_lint_reports_graph_relation_to_missing_node(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    state = ProjectState.load(runtime.state_dir)
    state.upsert_node(
        {
            "id": "concept:known",
            "kind": "concept",
            "title": "Known",
            "summary": "Known node.",
            "sources": ["raw/source.md"],
            "status": "staged",
            "staged_path": "staging/concepts/known.md",
        }
    )
    state.upsert_relation(
        {
            "id": "concept:known->supports->concept:missing",
            "source": "concept:known",
            "target": "concept:missing",
            "type": "supports",
            "sources": ["raw/source.md"],
            "status": "staged",
        }
    )

    result = lint_vault(runtime)

    assert any(issue.issue_type == "graph_broken_relation" for issue in result.issues)


def test_graph_candidate_with_content_and_key_points(tmp_path: Path) -> None:
    """Nodes with content and key_points should pass validation and appear in staged pages."""
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nRich content source.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)

    candidate_path = runtime.staging_dir / "graph" / "candidates" / "rich.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:rich-node",
                        "kind": "concept",
                        "title": "Rich Node",
                        "summary": "一个有丰富内容的知识点。",
                        "content": "这是一个详细的多段落解释。\n\n第二段包含了更多细节和例子。\n\n第三段讨论了与其他概念的关系。",
                        "key_points": [
                            "第一个关键要点：核心机制的解释。",
                            "第二个关键要点：实际应用场景。",
                            "第三个关键要点：与现有方法的对比。",
                        ],
                        "sources": ["raw/source.md"],
                        "theme": "Testing",
                        "subtheme": "Content Quality",
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "rich-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "rich-run",
                "output_path": "staging/graph/candidates/rich.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    result = consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="rich-consume")

    staged_page = runtime.staging_dir / "concepts" / "rich-node.md"
    assert staged_page.is_file()
    page_text = staged_page.read_text(encoding="utf-8")
    assert "## Content" in page_text
    assert "这是一个详细的多段落解释。" in page_text
    assert "## Key Points" in page_text
    assert "第一个关键要点" in page_text
    assert "第二个关键要点" in page_text

    state = ProjectState.load(runtime.state_dir)
    node = state.nodes()["concept:rich-node"]
    assert node["content"] == "这是一个详细的多段落解释。\n\n第二段包含了更多细节和例子。\n\n第三段讨论了与其他概念的关系。"
    assert len(node["key_points"]) == 3


def test_graph_candidate_rejects_invalid_content_type(tmp_path: Path) -> None:
    """content must be a string if provided."""
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nBody.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)

    candidate_path = runtime.staging_dir / "graph" / "candidates" / "bad.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:bad-content",
                        "kind": "concept",
                        "title": "Bad Content",
                        "summary": "Has invalid content field.",
                        "content": 123,
                        "sources": ["raw/source.md"],
                    }
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "bad-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "bad-run",
                "output_path": "staging/graph/candidates/bad.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodexResultError, match="content must be a string"):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="bad-consume")


# ---------------------------------------------------------------------------
# Phase 1 borrowed-from-graphify additions: confidence, update_action_hint,
# deterministic ids.
# ---------------------------------------------------------------------------


def test_normalize_node_id_ascii_title() -> None:
    assert normalize_node_id("concept", "Codex Graph Candidate") == "concept:codex-graph-candidate"


def test_normalize_node_id_preserves_cjk() -> None:
    assert normalize_node_id("concept", "TellMe 控制面") == "concept:tellme-控制面"


def test_normalize_node_id_collapses_punctuation_and_whitespace() -> None:
    assert normalize_node_id("entity", "  OpenAI / Anthropic: APIs  ") == "entity:openai-anthropic-apis"


def test_normalize_node_id_strips_adjacent_hyphens() -> None:
    assert normalize_node_id("concept", "---Edge---Case---") == "concept:edge-case"


def test_normalize_node_id_empty_title_falls_back_to_kind() -> None:
    assert normalize_node_id("concept", "   ") == "concept"


def _basic_candidate(node: dict, claims: list[dict] | None = None, relations: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "candidate_type": "knowledge_graph_update",
        "source_references": ["raw/source.md"],
        "nodes": [node],
        "claims": claims or [],
        "relations": relations or [],
        "conflicts": [],
    }


def _write_candidate_and_result(runtime, candidate: dict, run_suffix: str) -> Path:
    candidate_path = runtime.staging_dir / "graph" / "candidates" / f"{run_suffix}.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
    result_path = runtime.runs_dir / f"{run_suffix}-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": f"{run_suffix}-run",
                "output_path": f"staging/graph/candidates/{run_suffix}.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )
    return result_path


def _seed_runtime_with_source(tmp_path: Path):
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nBody.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)
    return runtime


def test_graph_candidate_accepts_confidence_on_claims_and_relations(tmp_path: Path) -> None:
    runtime = _seed_runtime_with_source(tmp_path)
    candidate = _basic_candidate(
        node={
            "id": "concept:alpha",
            "kind": "concept",
            "title": "Alpha",
            "summary": "Alpha summary.",
            "sources": ["raw/source.md"],
        },
        claims=[
            {
                "id": "claim:alpha-asserts",
                "subject": "concept:alpha",
                "text": "Alpha asserts X.",
                "sources": ["raw/source.md"],
                "confidence": "extracted",
                "confidence_score": 0.92,
            }
        ],
        relations=[
            {
                "source": "concept:alpha",
                "target": "concept:beta",
                "type": "depends_on",
                "sources": ["raw/source.md"],
                "confidence": "inferred",
                "confidence_score": 0.55,
            }
        ],
    )
    result_path = _write_candidate_and_result(runtime, candidate, "confidence-ok")
    consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="confidence-ok-consume")

    state = ProjectState.load(runtime.state_dir)
    claim = state.claims()["claim:alpha-asserts"]
    assert claim["confidence"] == "extracted"
    assert claim["confidence_score"] == 0.92
    relation = state.relations()["concept:alpha->depends_on->concept:beta"]
    assert relation["confidence"] == "inferred"
    assert relation["confidence_score"] == 0.55

    staged_page = (runtime.staging_dir / "concepts" / "alpha.md").read_text(encoding="utf-8")
    assert "[confidence: extracted, 0.92]" in staged_page
    assert "[confidence: inferred, 0.55]" in staged_page


def test_graph_candidate_rejects_invalid_confidence_label(tmp_path: Path) -> None:
    runtime = _seed_runtime_with_source(tmp_path)
    candidate = _basic_candidate(
        node={
            "id": "concept:alpha",
            "kind": "concept",
            "title": "Alpha",
            "summary": "Alpha summary.",
            "sources": ["raw/source.md"],
        },
        claims=[
            {
                "id": "claim:alpha",
                "subject": "concept:alpha",
                "text": "Alpha.",
                "sources": ["raw/source.md"],
                "confidence": "probably",  # invalid
            }
        ],
    )
    result_path = _write_candidate_and_result(runtime, candidate, "bad-confidence-label")
    with pytest.raises(CodexResultError, match="confidence must be one of"):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="x")


def test_graph_candidate_rejects_confidence_score_out_of_range(tmp_path: Path) -> None:
    runtime = _seed_runtime_with_source(tmp_path)
    candidate = _basic_candidate(
        node={
            "id": "concept:alpha",
            "kind": "concept",
            "title": "Alpha",
            "summary": "Alpha summary.",
            "sources": ["raw/source.md"],
        },
        relations=[
            {
                "source": "concept:alpha",
                "target": "concept:beta",
                "type": "supports",
                "sources": ["raw/source.md"],
                "confidence_score": 1.5,
            }
        ],
    )
    result_path = _write_candidate_and_result(runtime, candidate, "bad-confidence-score")
    with pytest.raises(CodexResultError, match="confidence_score must be between 0 and 1"):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="x")


def test_graph_candidate_honors_uncertain_update_action_hint(tmp_path: Path) -> None:
    runtime = _seed_runtime_with_source(tmp_path)
    candidate = _basic_candidate(
        node={
            "id": "concept:ambiguous",
            "kind": "concept",
            "title": "Ambiguous",
            "summary": "Not sure whether this is a new node.",
            "sources": ["raw/source.md"],
            "update_action_hint": "uncertain",
        }
    )
    result_path = _write_candidate_and_result(runtime, candidate, "uncertain-hint")
    consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="uncertain-consume")

    state = ProjectState.load(runtime.state_dir)
    node = state.nodes()["concept:ambiguous"]
    assert node["update_action"] == "uncertain"
    page_text = (runtime.staging_dir / "concepts" / "ambiguous.md").read_text(encoding="utf-8")
    assert "update_action: uncertain" in page_text


def test_graph_candidate_rejects_invalid_update_action_hint(tmp_path: Path) -> None:
    runtime = _seed_runtime_with_source(tmp_path)
    candidate = _basic_candidate(
        node={
            "id": "concept:alpha",
            "kind": "concept",
            "title": "Alpha",
            "summary": "Alpha.",
            "sources": ["raw/source.md"],
            "update_action_hint": "replace",  # not a valid action
        }
    )
    result_path = _write_candidate_and_result(runtime, candidate, "bad-hint")
    with pytest.raises(CodexResultError, match="update_action_hint must be one of"):
        consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="x")
