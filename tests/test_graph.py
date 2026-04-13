from __future__ import annotations

import json
from pathlib import Path

import pytest

from tellme.codex import CodexResultError, consume_codex_result
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
