from __future__ import annotations

import json
from pathlib import Path

from tellme.codex import consume_codex_result
from tellme.config import load_runtime
from tellme.ingest import ingest_file
from tellme.project import init_project
from tellme.publish import PublishError, publish_staged_graph
from tellme.reader_rewrite import consume_reader_rewrite_result, create_reader_rewrite_handoff
from tellme.query import query_vault
from tellme.runs import RunStore
from tellme.state import ContentStatus, PageRecord, ProjectState


def test_publish_staged_graph_page_to_vault_and_updates_state(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    staged_page = _stage_graph_candidate(runtime=runtime, tmp_path=tmp_path)

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex", staged_path=staged_page)

    assert result.published_pages == ["wiki/references/codex-graph-candidate.md"]
    vault_page = runtime.wiki_dir / "references" / "codex-graph-candidate.md"
    assert vault_page.is_file()
    vault_text = vault_page.read_text(encoding="utf-8")
    assert "status: published" in vault_text
    assert "last_run_id: publish-run" in vault_text

    state = ProjectState.load(runtime.state_dir)
    page = state.get_page("wiki/references/codex-graph-candidate.md")
    assert page.status == ContentStatus.PUBLISHED
    assert page.published_path == "wiki/references/codex-graph-candidate.md"
    node = state.nodes()["concept:codex-graph-candidate"]
    assert node["status"] == "published"
    assert node["published_path"] == "wiki/references/codex-graph-candidate.md"
    assert node["staged_path"] == "staging/concepts/codex-graph-candidate.md"


def test_publish_staged_graph_all_publishes_each_staged_node(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    _stage_graph_candidate(runtime=runtime, tmp_path=tmp_path)

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["wiki/references/codex-graph-candidate.md"]


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
        publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex", staged_path="wiki/unsafe.md")
    except PublishError as exc:
        assert "staging/" in str(exc)
    else:
        raise AssertionError("publish should reject non-staging paths")


def test_publish_all_publishes_staged_synthesis_page(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    vault_source = runtime.wiki_dir / "concepts" / "alpha.md"
    vault_source.parent.mkdir(parents=True)
    vault_source.write_text(
        "---\npage_type: concept\nsources:\n  - raw/source.md\n---\n# Alpha\n\nReusable alpha context.",
        encoding="utf-8",
    )
    run = RunStore(runtime.runs_dir).start("query", "codex")
    query_vault(runtime=runtime, question="alpha context", run_id=run.run_id, host="codex", stage=True)

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["wiki/synthesis/alpha-context.md"]
    assert (runtime.wiki_dir / "synthesis" / "alpha-context.md").is_file()
    state = ProjectState.load(runtime.state_dir)
    assert state.get_page("wiki/synthesis/alpha-context.md").status == ContentStatus.PUBLISHED
    assert state.syntheses()["synthesis:alpha-context"]["status"] == "published"
    assert state.syntheses()["synthesis:alpha-context"]["published_path"] == "wiki/synthesis/alpha-context.md"
    assert (runtime.wiki_dir / "index.md").is_file()
    assert (runtime.wiki_dir / "indexes" / "synthesis.md").is_file()


def test_publish_all_publishes_staged_output_page(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    staged = runtime.staging_dir / "outputs" / "research-brief.md"
    staged.parent.mkdir(parents=True)
    staged.write_text(
        "---\npage_type: output\nstatus: staged\nsources:\n  - wiki/concepts/alpha.md\n---\n# Research Brief\n",
        encoding="utf-8",
    )
    state = ProjectState.load(runtime.state_dir)
    state.upsert_page(
        PageRecord(
            path="staging/outputs/research-brief.md",
            page_type="output",
            status=ContentStatus.STAGED,
            sha256="test-hash",
            sources=["wiki/concepts/alpha.md"],
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
            "sources": ["wiki/concepts/alpha.md"],
            "staged_path": "staging/outputs/research-brief.md",
            "last_host": "codex",
            "last_run_id": "run-1",
        }
    )

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["wiki/outputs/research-brief.md"]
    assert (runtime.wiki_dir / "outputs" / "research-brief.md").is_file()
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
    assert not (runtime.wiki_dir / "conflicts" / "review-me.md").exists()


def test_publish_generates_reader_facing_theme_subtheme_and_reference_pages(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nReader-facing organization.", encoding="utf-8")
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
                    },
                    {
                        "id": "entity:codex",
                        "kind": "entity",
                        "title": "Codex",
                        "summary": "Codex host summary.",
                        "sources": ["raw/source.md"],
                        "theme": "Architecture",
                        "subtheme": "Hosts",
                        "reader_role": "reference",
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

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["wiki/references/codex.md"]
    assert (runtime.wiki_dir / "references" / "codex.md").is_file()
    assert (runtime.wiki_dir / "themes" / "architecture.md").is_file()
    assert (runtime.wiki_dir / "subthemes" / "architecture-control-plane.md").is_file()
    assert (runtime.wiki_dir / "subthemes" / "architecture-hosts.md").is_file()


def test_create_reader_rewrite_handoff_writes_task_and_template(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    state = ProjectState.load(runtime.state_dir)
    state.upsert_node(
        {
            "id": "concept:tellme-control-plane",
            "kind": "concept",
            "title": "TellMe Control Plane",
            "summary": "Control plane summary.",
            "status": "published",
            "sources": ["raw/source.md"],
            "theme": "Architecture",
            "subtheme": "Control Plane",
            "reader_role": "embedded",
        }
    )
    generate = create_reader_rewrite_handoff(runtime=runtime, run_id="rewrite-run", host="codex")

    assert generate.task_markdown_path == "runs/rewrite-run/host-tasks/reader-rewrite-codex.md"
    assert generate.result_template_path == "runs/rewrite-run/artifacts/reader-rewrite.template.json"
    task_markdown = runtime.resolve_path(generate.task_markdown_path).read_text(encoding="utf-8")
    assert "TellMe Reader Rewrite Task" in task_markdown
    assert "wiki/index.md" in task_markdown
    assert "Page Role Contracts" in task_markdown
    assert "Overview" in task_markdown
    assert "Theme" in task_markdown
    assert "Reference" in task_markdown
    assert "Anti-patterns to remove" in task_markdown
    template = json.loads(runtime.resolve_path(generate.result_template_path).read_text(encoding="utf-8"))
    assert template["candidate_type"] == "reader_page_rewrites"
    assert template["rewrites"] == []


def test_consume_reader_rewrite_result_stages_reader_pages(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    result_path = runtime.staging_dir / "reader-rewrite" / "rewrite.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "reader_page_rewrites",
                "run_id": "rewrite-run",
                "host": "codex",
                "rewrites": [
                    {
                        "page_type": "theme",
                        "target_path": "staging/reader-rewrite/themes/architecture.md",
                        "sources": ["raw/source.md"],
                        "content": "---\npage_type: theme\nstatus: staged\nsources: [raw/source.md]\n---\n# Architecture\n\nRewrite body.\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = consume_reader_rewrite_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    assert result.staged_pages == ["staging/reader-rewrite/themes/architecture.md"]
    assert (runtime.staging_dir / "reader-rewrite" / "themes" / "architecture.md").is_file()
    page = ProjectState.load(runtime.state_dir).get_page("staging/reader-rewrite/themes/architecture.md")
    assert page.page_type == "theme"
    assert page.status == ContentStatus.STAGED


def test_publish_all_publishes_staged_reader_rewrite_pages(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    result_path = runtime.staging_dir / "reader-rewrite" / "rewrite.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "reader_page_rewrites",
                "run_id": "rewrite-run",
                "host": "codex",
                "rewrites": [
                    {
                        "page_type": "theme",
                        "target_path": "staging/reader-rewrite/themes/architecture.md",
                        "sources": ["raw/source.md"],
                        "content": "---\npage_type: theme\nstatus: staged\nsources: [raw/source.md]\n---\n# Architecture\n\nRewritten theme body.\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    consume_reader_rewrite_result(runtime=runtime, result_path=result_path, consume_run_id="consume-run")

    result = publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    assert result.published_pages == ["wiki/themes/architecture.md"]
    theme_text = (runtime.wiki_dir / "themes" / "architecture.md").read_text(encoding="utf-8")
    assert "Rewritten theme body." in theme_text


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


def test_publish_all_skips_nodes_flagged_uncertain(tmp_path: Path) -> None:
    """Nodes flagged uncertain by the LLM should stay staged and not appear in wiki/."""
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")

    source = tmp_path / "source.md"
    source.write_text("# Source\n\nBody.", encoding="utf-8")
    ingest_run = RunStore(runtime.runs_dir).start("ingest", "codex")
    ingest_file(runtime, source, ingest_run.run_id)

    candidate_path = runtime.staging_dir / "graph" / "candidates" / "mixed.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": ["raw/source.md"],
                "nodes": [
                    {
                        "id": "concept:confident-one",
                        "kind": "concept",
                        "title": "Confident One",
                        "summary": "Clearly a new concept.",
                        "sources": ["raw/source.md"],
                    },
                    {
                        "id": "concept:unsure-one",
                        "kind": "concept",
                        "title": "Unsure One",
                        "summary": "Not sure if this duplicates an existing node.",
                        "sources": ["raw/source.md"],
                        "update_action_hint": "uncertain",
                    },
                ],
                "claims": [],
                "relations": [],
                "conflicts": [],
            }
        ),
        encoding="utf-8",
    )
    result_path = runtime.runs_dir / "mixed-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "mixed-run",
                "output_path": "staging/graph/candidates/mixed.json",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )
    consume_codex_result(runtime=runtime, result_path=result_path, consume_run_id="mixed-consume")

    publish_staged_graph(runtime=runtime, run_id="publish-run", host="codex")

    # Confident node published
    assert (runtime.wiki_dir / "references" / "confident-one.md").is_file()
    # Uncertain node NOT published
    assert not (runtime.wiki_dir / "references" / "unsure-one.md").exists()

    state = ProjectState.load(runtime.state_dir)
    # Uncertain node still staged (not promoted)
    assert state.get_page("staging/concepts/unsure-one.md").status == ContentStatus.STAGED
    assert state.nodes()["concept:unsure-one"]["update_action"] == "uncertain"
