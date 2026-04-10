from __future__ import annotations

import subprocess
import sys
import os
import json
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
    for command in ["init", "ingest", "compile", "query", "lint", "reconcile", "publish"]:
        assert command in result.stdout


def test_init_creates_project_layout_and_machine_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))

    result = run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    for directory in [
        "config/hosts",
        "config/machines",
        "config/policies",
        "docs",
        "hosts",
        "templates",
    ]:
        assert (project_root / directory).is_dir()
    for directory in ["raw", "runs", "staging", "state", "vault"]:
        assert not (project_root / directory).exists()
        assert (data_root / directory).is_dir()

    assert (project_root / "config" / "project.toml").is_file()
    assert (project_root / "config" / "machines" / "test-pc.toml").is_file()
    assert (data_root / "state" / "manifest.json").is_file()
    assert (data_root / "runs" / ".gitkeep").is_file()


def test_workflow_command_resolves_explicit_project(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "lint", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert str((data_root / "vault").resolve()) in result.stdout


def test_workflow_command_fails_outside_project(tmp_path: Path) -> None:
    result = run_cli("lint", cwd=tmp_path)

    assert result.returncode != 0
    assert "not inside a TellMe project" in result.stderr


def test_cli_compile_and_query_are_usable_workflows(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
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


def test_cli_query_stage_writes_synthesis_candidate(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nAlpha content for TellMe.", encoding="utf-8")
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)
    run_cli("--project", str(project_root), "ingest", str(source), cwd=tmp_path)
    run_cli("--project", str(project_root), "compile", cwd=tmp_path)

    query_result = run_cli("--project", str(project_root), "query", "alpha", "--stage", cwd=tmp_path)

    assert query_result.returncode == 0, query_result.stderr
    assert "tellme query: staged staging/synthesis/alpha.md" in query_result.stdout
    assert (data_root / "staging" / "synthesis" / "alpha.md").is_file()


def test_cli_compile_reports_staged_pages_when_policy_disables_direct_publish(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nNeeds review.", encoding="utf-8")
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)
    (project_root / "config" / "policies" / "publish.toml").write_text(
        "[publish]\nsource_summary_direct_publish = false\n",
        encoding="utf-8",
    )
    run_cli("--project", str(project_root), "ingest", str(source), cwd=tmp_path)

    result = run_cli("--project", str(project_root), "compile", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "tellme compile: published 0 page(s)" in result.stdout
    assert "tellme compile: staged 1 page(s)" in result.stdout
    assert "staging/sources/source.md" in result.stdout


def test_cli_compile_codex_handoff_and_consume_result(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nCodex handoff source.", encoding="utf-8")
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)
    run_cli("--project", str(project_root), "ingest", str(source), cwd=tmp_path)

    handoff = run_cli("--project", str(project_root), "--host", "codex", "compile", "--handoff", cwd=tmp_path)

    assert handoff.returncode == 0, handoff.stderr
    assert "tellme compile: codex task" in handoff.stdout
    task_line = next(line for line in handoff.stdout.splitlines() if line.endswith("compile-codex.md"))
    assert (data_root / task_line).is_file()

    staged = data_root / "staging" / "codex" / "draft.md"
    staged.parent.mkdir(parents=True)
    staged.write_text("---\npage_type: synthesis\nsources:\n  - raw/source.md\n---\n# Draft", encoding="utf-8")
    result_path = data_root / "runs" / "codex-result.json"
    result_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "succeeded",
                "host": "codex",
                "run_id": "handoff-run",
                "output_path": "staging/codex/draft.md",
                "source_references": ["raw/source.md"],
            }
        ),
        encoding="utf-8",
    )

    consumed = run_cli(
        "--project",
        str(project_root),
        "--host",
        "codex",
        "compile",
        "--consume-result",
        "runs/codex-result.json",
        cwd=tmp_path,
    )

    assert consumed.returncode == 0, consumed.stderr
    assert "tellme compile: consumed codex result staging/codex/draft.md" in consumed.stdout


def test_cli_compile_consumes_codex_graph_candidate(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nCodex graph candidate source.", encoding="utf-8")
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)
    run_cli("--project", str(project_root), "ingest", str(source), cwd=tmp_path)

    handoff = run_cli("--project", str(project_root), "--host", "codex", "compile", "--handoff", cwd=tmp_path)

    assert handoff.returncode == 0, handoff.stderr
    candidate = data_root / "staging" / "graph" / "candidates" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(
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
    result_path = data_root / "runs" / "codex-graph-result.json"
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

    consumed = run_cli(
        "--project",
        str(project_root),
        "--host",
        "codex",
        "compile",
        "--consume-result",
        "runs/codex-graph-result.json",
        cwd=tmp_path,
    )

    assert consumed.returncode == 0, consumed.stderr
    assert "tellme compile: consumed codex result staging/concepts/codex-graph-candidate.md" in consumed.stdout
    assert (data_root / "staging" / "concepts" / "codex-graph-candidate.md").is_file()


def test_cli_publish_all_publishes_staged_graph_nodes(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nCodex graph candidate source.", encoding="utf-8")
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)
    run_cli("--project", str(project_root), "ingest", str(source), cwd=tmp_path)
    candidate = data_root / "staging" / "graph" / "candidates" / "candidate.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(
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
    result_path = data_root / "runs" / "codex-graph-result.json"
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
    run_cli(
        "--project",
        str(project_root),
        "--host",
        "codex",
        "compile",
        "--consume-result",
        "runs/codex-graph-result.json",
        cwd=tmp_path,
    )

    published = run_cli("--project", str(project_root), "--host", "codex", "publish", "--all", cwd=tmp_path)

    assert published.returncode == 0, published.stderr
    assert "tellme publish: published 1 page(s)" in published.stdout
    assert "vault/concepts/codex-graph-candidate.md" in published.stdout
    assert (data_root / "vault" / "concepts" / "codex-graph-candidate.md").is_file()


def test_cli_publish_all_publishes_staged_query_synthesis(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nAlpha content for TellMe.", encoding="utf-8")
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)
    run_cli("--project", str(project_root), "ingest", str(source), cwd=tmp_path)
    run_cli("--project", str(project_root), "compile", cwd=tmp_path)
    run_cli("--project", str(project_root), "query", "alpha", "--stage", cwd=tmp_path)

    published = run_cli("--project", str(project_root), "--host", "codex", "publish", "--all", cwd=tmp_path)

    assert published.returncode == 0, published.stderr
    assert "tellme publish: published 1 page(s)" in published.stdout
    assert "vault/synthesis/alpha.md" in published.stdout
    assert (data_root / "vault" / "synthesis" / "alpha.md").is_file()


def test_cli_lint_health_handoff_writes_host_task(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "tellme-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "--host", "codex", "lint", "--health-handoff", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "tellme lint: health task" in result.stdout
    task_line = next(line for line in result.stdout.splitlines() if line.endswith("health-codex.md"))
    assert (data_root / task_line).is_file()


def test_cli_compile_handoff_requires_codex_host(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    run_cli("init", str(project_root), "--machine", "test-pc", cwd=tmp_path)

    result = run_cli("--project", str(project_root), "--host", "opencode", "compile", "--handoff", cwd=tmp_path)

    assert result.returncode == 2
    assert "--handoff and --consume-result require --host codex" in result.stderr
