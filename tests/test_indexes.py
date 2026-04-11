from __future__ import annotations

from pathlib import Path

from tellme.config import load_runtime
from tellme.indexes import generate_vault_indexes
from tellme.project import init_project
from tellme.state import ContentStatus, PageRecord, ProjectState


def test_generate_vault_indexes_links_published_graph_and_synthesis_pages(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    _seed_index_state(runtime)

    result = generate_vault_indexes(runtime=runtime, run_id="index-run", host="codex")

    assert result.index_pages == [
        "vault/index.md",
        "vault/themes/architecture.md",
        "vault/subthemes/architecture-control-plane.md",
        "vault/references/codex-graph-candidate.md",
        "vault/indexes/concepts.md",
        "vault/indexes/entities.md",
        "vault/indexes/synthesis.md",
        "vault/indexes/unresolved-conflicts.md",
        "vault/indexes/health-review.md",
    ]
    root_index = (runtime.vault_dir / "index.md").read_text(encoding="utf-8")
    assert "TellMe Knowledge Base" in root_index
    assert "## Summary" in root_index
    assert "## Recommended Reading Path" in root_index
    assert "## Theme Map" in root_index
    assert "## Thin Areas" in root_index
    assert "themes/architecture.md" in root_index
    assert "references/codex-graph-candidate.md" in root_index
    assert "indexes/health-review.md" in root_index
    theme = (runtime.vault_dir / "themes" / "architecture.md").read_text(encoding="utf-8")
    assert "## Summary" in theme
    assert "## Why This Theme Matters" in theme
    assert "## Core Question" in theme
    assert "## Narrative" in theme
    assert "## Key Claims" in theme
    assert "## Relationships" in theme
    assert "## Evidence" in theme
    assert "Control planes organize published knowledge." in theme
    assert "depends_on" in theme
    assert "This theme centers on" in theme
    assert "Control Plane" in theme
    assert "Codex Graph Candidate" in theme
    subtheme = (runtime.vault_dir / "subthemes" / "architecture-control-plane.md").read_text(encoding="utf-8")
    assert "## Summary" in subtheme
    assert "## How This Fits" in subtheme
    assert "## Narrative" in subtheme
    assert "## Key Claims" in subtheme
    assert "## Evidence" in subtheme
    assert "Control planes organize published knowledge." in subtheme
    assert "Within this subtheme" in subtheme
    assert "TellMe Control Plane" in subtheme
    reference = (runtime.vault_dir / "references" / "codex-graph-candidate.md").read_text(encoding="utf-8")
    assert "page_type: reference" in reference
    concepts = (runtime.vault_dir / "indexes" / "concepts.md").read_text(encoding="utf-8")
    assert "Codex Graph Candidate" in concepts
    assert "../references/codex-graph-candidate.md" in concepts
    synthesis = (runtime.vault_dir / "indexes" / "synthesis.md").read_text(encoding="utf-8")
    assert "Alpha Synthesis" in synthesis
    conflicts = (runtime.vault_dir / "indexes" / "unresolved-conflicts.md").read_text(encoding="utf-8")
    assert "Needs Review" in conflicts
    health = (runtime.vault_dir / "indexes" / "health-review.md").read_text(encoding="utf-8")
    assert "Thin Node Needs Enrichment" in health
    assert "../../staging/health/health-thin-node-needs-enrichment.md" in health

    state = ProjectState.load(runtime.state_dir)
    assert state.get_page("vault/index.md").page_type == "overview"
    assert state.indexes()["vault/index.md"]["last_run_id"] == "index-run"


def test_generate_vault_indexes_handles_empty_state(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")

    generate_vault_indexes(runtime=runtime, run_id="index-run", host="codex")

    concepts = (runtime.vault_dir / "indexes" / "concepts.md").read_text(encoding="utf-8")
    assert "No published concepts yet." in concepts
    conflicts = (runtime.vault_dir / "indexes" / "unresolved-conflicts.md").read_text(encoding="utf-8")
    assert "No unresolved conflicts." in conflicts
    health = (runtime.vault_dir / "indexes" / "health-review.md").read_text(encoding="utf-8")
    assert "No staged health findings." in health
    root = (runtime.vault_dir / "index.md").read_text(encoding="utf-8")
    assert "## Summary" in root
    assert "No reader-facing themes yet." in root


def test_generate_vault_indexes_removes_stale_reader_facing_pages(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, host="codex")
    stale_theme = runtime.vault_dir / "themes" / "old-theme.md"
    stale_theme.parent.mkdir(parents=True, exist_ok=True)
    stale_theme.write_text("# Old Theme\n", encoding="utf-8")
    state = ProjectState.load(runtime.state_dir)
    state.upsert_page(
        PageRecord(
            path="vault/themes/old-theme.md",
            page_type="theme",
            status=ContentStatus.PUBLISHED,
            sha256="seed",
            sources=[],
            last_host="codex",
            last_run_id="seed-run",
            published_path="vault/themes/old-theme.md",
        )
    )
    state.upsert_index(
        {
            "id": "vault/themes/old-theme.md",
            "path": "vault/themes/old-theme.md",
            "title": "Old Theme",
            "status": "published",
            "last_host": "codex",
            "last_run_id": "seed-run",
            "published_path": "vault/themes/old-theme.md",
        }
    )
    _seed_index_state(runtime)

    generate_vault_indexes(runtime=runtime, run_id="index-run", host="codex")

    assert not stale_theme.exists()
    refreshed = ProjectState.load(runtime.state_dir)
    assert "vault/themes/old-theme.md" not in refreshed.pages()
    assert "vault/themes/old-theme.md" not in refreshed.indexes()


def _seed_index_state(runtime) -> None:
    state = ProjectState.load(runtime.state_dir)
    state.upsert_node(
        {
            "id": "concept:codex-graph-candidate",
            "kind": "concept",
            "title": "Codex Graph Candidate",
            "status": "published",
            "sources": ["raw/source.md"],
            "published_path": "vault/references/codex-graph-candidate.md",
            "theme": "Architecture",
            "subtheme": "Control Plane",
            "reader_role": "reference",
        }
    )
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
    state.upsert_claim(
        {
            "id": "claim:control-planes-organize-published-knowledge",
            "subject": "concept:tellme-control-plane",
            "text": "Control planes organize published knowledge.",
            "sources": ["raw/source.md"],
            "status": "published",
        }
    )
    state.upsert_relation(
        {
            "id": "concept:tellme-control-plane->depends_on->concept:codex-graph-candidate",
            "source": "concept:tellme-control-plane",
            "target": "concept:codex-graph-candidate",
            "type": "depends_on",
            "sources": ["raw/source.md"],
            "status": "published",
        }
    )
    state.upsert_node(
        {
            "id": "entity:openai",
            "kind": "entity",
            "title": "OpenAI",
            "status": "published",
            "sources": ["raw/source.md"],
            "published_path": "vault/entities/openai.md",
        }
    )
    state.upsert_synthesis(
        {
            "id": "synthesis:alpha",
            "title": "Alpha Synthesis",
            "status": "published",
            "sources": ["vault/concepts/codex-graph-candidate.md"],
            "published_path": "vault/synthesis/alpha.md",
        }
    )
    state.upsert_conflict(
        {
            "id": "conflict:needs-review",
            "summary": "Needs Review",
            "status": "staged",
            "sources": ["raw/source.md"],
            "staged_path": "staging/conflicts/needs-review.md",
        }
    )
    state.upsert_health_finding(
        {
            "id": "health:thin-node-needs-enrichment",
            "finding_type": "thin_node",
            "summary": "Thin Node Needs Enrichment",
            "affected_ids": ["concept:codex-graph-candidate"],
            "sources": ["raw/source.md"],
            "recommendation": "Add stronger claims.",
            "confidence": "high",
            "suggested_next_action": "enrich_node",
            "status": "staged",
            "staged_path": "staging/health/health-thin-node-needs-enrichment.md",
            "last_host": "codex",
            "last_run_id": "seed-run",
        }
    )
    for path, page_type in [
        ("vault/references/codex-graph-candidate.md", "reference"),
        ("vault/entities/openai.md", "entity"),
        ("vault/synthesis/alpha.md", "synthesis"),
    ]:
        state.upsert_page(
            PageRecord(
                path=path,
                page_type=page_type,
                status=ContentStatus.PUBLISHED,
                sha256="seed",
                sources=["raw/source.md"],
                last_host="codex",
                last_run_id="seed-run",
                published_path=path,
            )
        )
