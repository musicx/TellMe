from __future__ import annotations

import json
from pathlib import Path

from tellme.codex import consume_codex_result
from tellme.config import load_runtime
from tellme.ingest import ingest_file
from tellme.project import init_project
from tellme.publish import PublishError, publish_staged_graph
from tellme.runs import RunStore
from tellme.state import ContentStatus, ProjectState


def test_publish_staged_graph_page_to_vault_and_updates_state(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    staged_page = _stage_graph_candidate(runtime=runtime, tmp_path=tmp_path)

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex", staged_path=staged_page)

    assert result.published_pages == ["vault/concepts/codex-graph-candidate.md"]
    vault_page = runtime.vault_dir / "concepts" / "codex-graph-candidate.md"
    assert vault_page.is_file()
    vault_text = vault_page.read_text(encoding="utf-8")
    assert "status: published" in vault_text
    assert "last_run_id: publish-run" in vault_text

    state = ProjectState.load(runtime.state_dir)
    page = state.get_page("vault/concepts/codex-graph-candidate.md")
    assert page.status == ContentStatus.PUBLISHED
    assert page.published_path == "vault/concepts/codex-graph-candidate.md"
    node = state.nodes()["concept:codex-graph-candidate"]
    assert node["status"] == "published"
    assert node["published_path"] == "vault/concepts/codex-graph-candidate.md"
    assert node["staged_path"] == "staging/concepts/codex-graph-candidate.md"


def test_publish_staged_graph_all_publishes_each_staged_node(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    _stage_graph_candidate(runtime=runtime, tmp_path=tmp_path)

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["vault/concepts/codex-graph-candidate.md"]


def test_publish_staged_graph_all_is_idempotent_after_state_update(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    _stage_graph_candidate(runtime=runtime, tmp_path=tmp_path)
    publish_staged_graph(runtime=runtime, run_id="publish-run-1", host="codex")

    result = publish_staged_graph(runtime=runtime, run_id="publish-run-2", host="codex")

    assert result.published_pages == []


def test_publish_rejects_non_staging_path(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")

    try:
        publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex", staged_path="vault/unsafe.md")
    except PublishError as exc:
        assert "staging/" in str(exc)
    else:
        raise AssertionError("publish should reject non-staging paths")


def _stage_graph_candidate(runtime, tmp_path: Path) -> str:
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nCodex graph candidate source.", encoding="utf-8")
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
    return consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run").staged_page
