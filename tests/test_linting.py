from __future__ import annotations

import os
from pathlib import Path

from tellme.config import load_runtime
from tellme.linting import lint_vault
from tellme.markdown import extract_wikilinks, parse_frontmatter
from tellme.project import init_project
from tellme.runs import RunStore
from tellme.state import ContentStatus, PageRecord, ProjectState


def test_parse_frontmatter_and_extract_wikilinks() -> None:
    page = "---\ntitle: Example\nsources: [raw/a.md]\n---\n# Example\nSee [[Other Page]]."

    frontmatter, body = parse_frontmatter(page)

    assert frontmatter["title"] == "Example"
    assert "See [[Other Page]]." in body
    assert extract_wikilinks(body) == {"Other Page"}


def test_lint_vault_reports_missing_frontmatter(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    (runtime.wiki_dir / "No Frontmatter.md").write_text("# No Frontmatter\n", encoding="utf-8")

    result = lint_vault(runtime)

    assert any(issue.issue_type == "missing_frontmatter" for issue in result.issues)


def test_lint_vault_reports_broken_wikilink(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    (runtime.wiki_dir / "Page.md").write_text(
        "---\ntitle: Page\nsources: [raw/page.md]\n---\nSee [[Missing Page]].",
        encoding="utf-8",
    )

    result = lint_vault(runtime)

    assert any(issue.issue_type == "broken_link" for issue in result.issues)


def test_lint_vault_accepts_wikilink_matching_page_heading(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    (runtime.wiki_dir / "tellme-control-plane.md").write_text(
        "---\npage_type: concept\nsources: [raw/page.md]\n---\n# TellMe Control Plane\n\nBody.\n",
        encoding="utf-8",
    )
    (runtime.wiki_dir / "health-reflection-loop.md").write_text(
        "---\npage_type: concept\nsources: [raw/page.md]\n---\n# Health Reflection Loop\n\nSee [[TellMe Control Plane]].\n",
        encoding="utf-8",
    )

    result = lint_vault(runtime)

    assert not any(issue.issue_type == "broken_link" for issue in result.issues)


def test_cli_lint_creates_run_record(tmp_path: Path, monkeypatch) -> None:
    from test_cli import run_cli
    from tellme.config import load_runtime

    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    runtime_root = tmp_path / "tellme-runtime"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    monkeypatch.setenv("TELLME_RUNTIME_ROOT", str(runtime_root))
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "lint", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    runtime = load_runtime(project_root=project_root)
    run_dirs = list(runtime.runs_dir.glob("*/run.json"))
    assert len(run_dirs) == 1


def test_lint_vault_reports_state_page_hash_drift(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    page = runtime.wiki_dir / "Page.md"
    page.write_text(
        "---\ntitle: Page\nsources: [raw/page.md]\n---\nOriginal.",
        encoding="utf-8",
    )
    state = ProjectState.load(runtime.state_dir)
    state.upsert_page(
        PageRecord(
            path="wiki/Page.md",
            page_type="note",
            status=ContentStatus.PUBLISHED,
            sha256="not-the-current-hash",
            sources=["raw/page.md"],
            last_host="codex",
            last_run_id="run-1",
            published_path="wiki/Page.md",
        )
    )
    result = lint_vault(runtime)

    assert any(issue.issue_type == "page_hash_drift" for issue in result.issues)


def test_lint_vault_reports_running_runs(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    RunStore(runtime.runs_dir).start("compile", "codex")

    result = lint_vault(runtime)

    assert any(issue.issue_type == "running_run" for issue in result.issues)


def test_lint_vault_can_ignore_current_run(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    run = RunStore(runtime.runs_dir).start("lint", "codex")

    result = lint_vault(runtime, current_run_id=run.run_id)

    assert not any(issue.issue_type == "running_run" for issue in result.issues)


def test_lint_vault_reports_health_finding_missing_affected_id_and_staged_page(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    state = ProjectState.load(runtime.state_dir)
    state.upsert_health_finding(
        {
            "id": "health:missing-node",
            "finding_type": "missing_node",
            "summary": "A missing concept should be reviewed.",
            "affected_ids": ["concept:missing"],
            "sources": ["raw/source.md"],
            "recommendation": "Create the missing concept.",
            "confidence": "high",
            "status": "staged",
            "staged_path": "staging/health/health-missing-node.md",
            "last_host": "codex",
            "last_run_id": "run-1",
        }
    )

    result = lint_vault(runtime)

    assert any(issue.issue_type == "health_missing_staged_page" for issue in result.issues)
    assert any(issue.issue_type == "health_unknown_affected_id" for issue in result.issues)
