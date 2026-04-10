from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "tellme", *args],
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )


def test_cli_help_lists_mvp_commands(tmp_path: Path) -> None:
    result = run_cli("--help", cwd=tmp_path)

    assert result.returncode == 0
    for command in ["init", "ingest", "compile", "query", "lint", "reconcile"]:
        assert command in result.stdout


def test_init_creates_project_layout_and_machine_config(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"

    result = run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    for directory in [
        "config/hosts",
        "config/machines",
        "config/policies",
        "docs",
        "hosts",
        "raw",
        "runs",
        "staging",
        "state",
        "templates",
        "vault",
    ]:
        assert (project_root / directory).is_dir()

    assert (project_root / "config" / "project.toml").is_file()
    assert (project_root / "config" / "machines" / "test-pc.toml").is_file()
    assert (project_root / "state" / "manifest.json").is_file()
    assert (project_root / "runs" / ".gitkeep").is_file()


def test_workflow_command_resolves_explicit_project(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "lint", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert str(project_root.resolve()) in result.stdout


def test_workflow_command_fails_outside_project(tmp_path: Path) -> None:
    result = run_cli("lint", cwd=tmp_path)

    assert result.returncode != 0
    assert "not inside a TellMe project" in result.stderr


def test_cli_compile_and_query_are_usable_workflows(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nAlpha content for TellMe.", encoding="utf-8")
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)
    run_cli("--project", str(project_root), "ingest", str(source), cwd=tmp_path)

    compile_result = run_cli("--project", str(project_root), "compile", cwd=tmp_path)

    assert compile_result.returncode == 0, compile_result.stderr
    assert "tellme compile: published 1 page(s)" in compile_result.stdout
    assert "implementation pending" not in compile_result.stdout

    query_result = run_cli("--project", str(project_root), "query", "alpha", cwd=tmp_path)

    assert query_result.returncode == 0, query_result.stderr
    assert "tellme query: wrote runs/" in query_result.stdout
    assert "implementation pending" not in query_result.stdout
