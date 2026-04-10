from __future__ import annotations

from pathlib import Path

from .state import ProjectState


PROJECT_DIRS = (
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
)


def init_project(project_root: Path, machine: str) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    for directory in PROJECT_DIRS:
        (project_root / directory).mkdir(parents=True, exist_ok=True)

    _write_if_missing(project_root / "config" / "project.toml", _project_toml())
    _write_if_missing(
        project_root / "config" / "machines" / f"{machine}.toml",
        _machine_toml(machine=machine, project_root=project_root),
    )
    _write_if_missing(project_root / "runs" / ".gitkeep", "")
    ProjectState.create(project_root / "state")


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _project_toml() -> str:
    return """[project]
name = "TellMe"
mode = "hybrid-orchestrator"
primary_vault = "primary_vault"

[layout]
raw_dir = "raw"
staging_dir = "staging"
state_dir = "state"
runs_dir = "runs"
vault_dir = "vault"
"""


def _machine_toml(machine: str, project_root: Path) -> str:
    root = str(project_root)
    return f"""[machine]
name = "{machine}"
platform = "{_platform_name()}"

[paths]
project_root = "{_toml_escape(root)}"
primary_vault = "{_toml_escape(str(project_root / "vault"))}"
raw_root = "{_toml_escape(str(project_root / "raw"))}"
staging_root = "{_toml_escape(str(project_root / "staging"))}"
state_root = "{_toml_escape(str(project_root / "state"))}"
runs_root = "{_toml_escape(str(project_root / "runs"))}"
"""


def _platform_name() -> str:
    import sys

    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return sys.platform


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
