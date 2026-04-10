from __future__ import annotations

import json
from pathlib import Path

from tellme.codex import consume_codex_result
from tellme.config import load_runtime
from tellme.ingest import ingest_file
from tellme.project import init_project
from tellme.publish import PublishError, publish_staged_graph
from tellme.query import query_vault
from tellme.runs import RunStore
from tellme.state import ContentStatus, PageRecord, ProjectState


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


def test_publish_all_publishes_staged_synthesis_page(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    vault_source = runtime.vault_dir / "concepts" / "alpha.md"
    vault_source.parent.mkdir(parents=True)
    vault_source.write_text(
        "---\npage_type: concept\nsources:\n  - raw/source.md\n---\n# Alpha\n\nReusable alpha context.",
        encoding="utf-8",
    )
    run = RunStore(runtime.runs_dir).start("query", "codex")
    query_vault(runtime=runtime, question="alpha context", run_id=run.run_id, host="codex", stage=True)

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["vault/synthesis/alpha-context.md"]
    assert (runtime.vault_dir / "synthesis" / "alpha-context.md").is_file()
    state = ProjectState.load(runtime.state_dir)
    assert state.get_page("vault/synthesis/alpha-context.md").status == ContentStatus.PUBLISHED
    assert state.syntheses()["synthesis:alpha-context"]["status"] == "published"
    assert state.syntheses()["synthesis:alpha-context"]["published_path"] == "vault/synthesis/alpha-context.md"
    assert (runtime.vault_dir / "index.md").is_file()
    assert (runtime.vault_dir / "indexes" / "synthesis.md").is_file()


def test_publish_all_publishes_staged_output_page(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    staged = runtime.staging_dir / "outputs" / "research-brief.md"
    staged.parent.mkdir(parents=True)
    staged.write_text(
        "---\npage_type: output\nstatus: staged\nsources:\n  - vault/concepts/alpha.md\n---\n# Research Brief\n",
        encoding="utf-8",
    )
    state = ProjectState.load(runtime.state_dir)
    state.upsert_page(
        PageRecord(
            path="staging/outputs/research-brief.md",
            page_type="output",
            status=ContentStatus.STAGED,
            sha256="test-hash",
            sources=["vault/concepts/alpha.md"],
            last_host="codex",
            last_run_id="run-1",
            staged_path="staging/outputs/research-brief.md",
        )
    )
    state.upsert_output(
        {
            "id": "output:research-brief",
            "kind": "research_brief",
            "title": "Research Brief",
            "status": "staged",
            "sources": ["vault/concepts/alpha.md"],
            "staged_path": "staging/outputs/research-brief.md",
            "last_host": "codex",
            "last_run_id": "run-1",
        }
    )

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["vault/outputs/research-brief.md"]
    assert (runtime.vault_dir / "outputs" / "research-brief.md").is_file()
    assert ProjectState.load(runtime.state_dir).outputs()["output:research-brief"]["status"] == "published"


def test_publish_all_skips_conflict_review_pages(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    conflict = runtime.staging_dir / "conflicts" / "review-me.md"
    conflict.parent.mkdir(parents=True)
    conflict.write_text(
        "---\npage_type: conflict\nstatus: staged\nsources:\n  - raw/source.md\n---\n# Review Me\n",
        encoding="utf-8",
    )
    ProjectState.load(runtime.state_dir).upsert_page(
        PageRecord(
            path="staging/conflicts/review-me.md",
            page_type="conflict",
            status=ContentStatus.STAGED,
            sha256="test-hash",
            sources=["raw/source.md"],
            last_host="codex",
            last_run_id="run-1",
            staged_path="staging/conflicts/review-me.md",
        )
    )

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == []
    assert not (runtime.vault_dir / "conflicts" / "review-me.md").exists()


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
