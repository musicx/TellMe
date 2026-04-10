from __future__ import annotations

from pathlib import Path

from tellme.config import load_runtime
from tellme.linting import lint_vault
from tellme.markdown import extract_wikilinks, parse_frontmatter
from tellme.project import init_project


def test_parse_frontmatter_and_extract_wikilinks() -> None:
    page = "---\ntitle: Example\nsources: [raw/a.md]\n---\n# Example\nSee [[Other Page]]."

    frontmatter, body = parse_frontmatter(page)

    assert frontmatter["title"] == "Example"
    assert "See [[Other Page]]." in body
    assert extract_wikilinks(body) == {"Other Page"}


def test_lint_vault_reports_missing_frontmatter(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    (project_root / "vault" / "No Frontmatter.md").write_text("# No Frontmatter\n", encoding="utf-8")
    runtime = load_runtime(project_root=project_root, machine="test-pc")

    result = lint_vault(runtime)

    assert any(issue.issue_type == "missing_frontmatter" for issue in result.issues)


def test_lint_vault_reports_broken_wikilink(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    (project_root / "vault" / "Page.md").write_text(
        "---\ntitle: Page\nsources: [raw/page.md]\n---\nSee [[Missing Page]].",
        encoding="utf-8",
    )
    runtime = load_runtime(project_root=project_root, machine="test-pc")

    result = lint_vault(runtime)

    assert any(issue.issue_type == "broken_link" for issue in result.issues)


def test_cli_lint_creates_run_record(tmp_path: Path) -> None:
    from test_cli import run_cli

    project_root = tmp_path / "TellMe"
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "lint", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    run_dirs = list((project_root / "runs").glob("*/run.json"))
    assert len(run_dirs) == 1
