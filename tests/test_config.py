from __future__ import annotations

from pathlib import Path

import pytest

from tellme.config import load_runtime
from tellme.project import init_project
from tellme.resolver import ProjectNotFoundError, resolve_project_root


def test_resolve_project_root_from_nested_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    nested = project_root / "docs" / "wiki"
    init_project(project_root, machine="test-pc")
    nested.mkdir(parents=True)

    assert resolve_project_root(start=nested) == project_root.resolve()


def test_load_runtime_uses_machine_path_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "data-root"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    init_project(project_root, machine="test-pc")

    runtime = load_runtime(project_root=project_root, machine="test-pc")

    assert runtime.project_root == project_root.resolve()
    assert runtime.data_root == data_root.resolve()
    assert runtime.raw_dir == data_root.resolve() / "raw"
    assert runtime.wiki_dir == data_root.resolve() / "wiki"
    assert runtime.project.name == "TellMe"
    assert runtime.machine is not None
    assert runtime.machine.name == "test-pc"


def test_init_creates_default_host_and_policy_configs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "TellMe"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "data-root"))
    init_project(project_root, machine="test-pc")

    for host in ["claude-code", "codex", "opencode"]:
        assert (project_root / "config" / "hosts" / f"{host}.toml").is_file()
    assert (project_root / "config" / "policies" / "publish.toml").is_file()
    assert (project_root / "config" / "policies" / "lint.toml").is_file()


def test_load_runtime_includes_selected_host_and_policies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "TellMe"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path / "data-root"))
    init_project(project_root, machine="test-pc")

    runtime = load_runtime(project_root=project_root, machine="test-pc", host="claude-code")

    assert runtime.host is not None
    assert runtime.host.name == "claude-code"
    assert runtime.host.preferred_model == "host-default"
    assert runtime.policies["publish"]["source_summary_direct_publish"] is True
    assert runtime.policies["lint"]["check_page_hash_drift"] is True


def test_load_runtime_uses_env_data_root_without_machine_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "TellMe"
    data_root = tmp_path / "external-data"
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(data_root))
    init_project(project_root, machine="test-pc")

    runtime = load_runtime(project_root=project_root)

    assert runtime.data_root == data_root.resolve()
    assert runtime.raw_dir == data_root.resolve() / "raw"
    assert runtime.runs_dir == data_root.resolve() / "runs"
    assert runtime.state_dir == data_root.resolve() / "state"
    assert runtime.staging_dir == data_root.resolve() / "staging"
    assert runtime.wiki_dir == data_root.resolve() / "wiki"


def test_load_runtime_falls_back_to_home_obsidian_data_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "TellMe"
    (project_root / "config").mkdir(parents=True)
    (project_root / "config" / "project.toml").write_text(
        "[project]\nname = \"TellMe\"\nmode = \"hybrid-orchestrator\"\nprimary_wiki = \"primary_wiki\"\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)

    runtime = load_runtime(project_root=project_root)

    assert runtime.data_root == (Path.home() / ".obsidian" / "llm_wiki").resolve()


def test_resolve_project_root_fails_outside_project(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        resolve_project_root(start=tmp_path)
