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
    (runtime.vault_dir / "No Frontmatter.md").write_text("# No Frontmatter\n", encoding="utf-8")

    result = lint_vault(runtime)

    assert any(issue.issue_type == "missing_frontmatter" for issue in result.issues)


def test_lint_vault_reports_broken_wikilink(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    (runtime.vault_dir / "Page.md").write_text(
        "---\ntitle: Page\nsources: [raw/page.md]\n---\nSee [[Missing Page]].",
        encoding="utf-8",
    )

    result = lint_vault(runtime)

    assert any(issue.issue_type == "broken_link" for issue in result.issues)


def test_cli_lint_creates_run_record(tmp_path: Path) -> None:
    from test_cli import run_cli

    project_root = tmp_path / "TellMe"
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "lint", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    data_root = Path(os.environ["OBSIDIAN_VAULT_PATH"])
    run_dirs = list((data_root / "runs").glob("*/run.json"))
    assert len(run_dirs) == 1


def test_lint_vault_reports_state_page_hash_drift(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    runtime = load_runtime(project_root=project_root, machine="test-pc")
    page = runtime.vault_dir / "Page.md"
    page.write_text(
        "---\ntitle: Page\nsources: [raw/page.md]\n---\nOriginal.",
        encoding="utf-8",
    )
    state = ProjectState.load(runtime.state_dir)
    state.upsert_page(
        PageRecord(
            path="vault/Page.md",
            page_type="note",
            status=ContentStatus.PUBLISHED,
            sha256="not-the-current-hash",
            sources=["raw/page.md"],
            last_host="codex",
            last_run_id="run-1",
            published_path="vault/Page.md",
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
