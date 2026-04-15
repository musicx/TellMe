from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .state import ProjectState


CONTROL_DIRS = (
    "config/hosts",
    "config/machines",
    "config/policies",
    "docs",
    "hosts",
    "templates",
)


def init_project(project_root: Path, machine: str) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    for directory in CONTROL_DIRS:
        (project_root / directory).mkdir(parents=True, exist_ok=True)

    _write_if_missing(project_root / "config" / "project.toml", _project_toml())
    for host in ("claude-code", "codex", "opencode"):
        _write_if_missing(project_root / "config" / "hosts" / f"{host}.toml", _host_toml(host))
    _write_if_missing(project_root / "config" / "policies" / "lint.toml", _lint_policy_toml())
    _write_if_missing(
        project_root / "config" / "machines" / f"{machine}.toml",
        _machine_toml(machine=machine, project_root=project_root),
    )
    data_paths = _data_paths(project_root=project_root, machine=machine)
    for key in ("raw_root", "staging_root", "state_root", "runs_root", "primary_wiki"):
        data_paths[key].mkdir(parents=True, exist_ok=True)
    _write_if_missing(data_paths["runs_root"] / ".gitkeep", "")
    ProjectState.create(data_paths["state_root"])


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _project_toml() -> str:
    return """[project]
name = "TellMe"
mode = "hybrid-orchestrator"
primary_wiki = "primary_wiki"

[data]
root_env = "OBSIDIAN_VAULT_PATH"
fallback_root = "~/.obsidian/llm_wiki"
runtime_root_env = "TELLME_RUNTIME_ROOT"
runtime_fallback_root = "~/.tmp/tellme"

[layout]
raw_dir = "raw"
staging_dir = "staging"
state_dir = "state"
runs_dir = "runs"
wiki_dir = "wiki"
"""


def _host_toml(host: str) -> str:
    return f"""[host]
name = "{host}"
preferred_model = "host-default"
command_profile = "default"
"""


def _lint_policy_toml() -> str:
    return """[lint]
check_page_hash_drift = true
check_running_runs = true
"""


def _machine_toml(machine: str, project_root: Path) -> str:
    root = str(project_root)
    data_root = _default_data_root()
    runtime_root = _default_runtime_root(project_root)
    return f"""[machine]
name = "{machine}"
platform = "{_platform_name()}"

[paths]
project_root = "{_toml_escape(root)}"
primary_wiki = "{_toml_escape(str(data_root / "wiki"))}"
wiki_root = "{_toml_escape(str(data_root / "wiki"))}"
raw_root = "{_toml_escape(str(data_root / "raw"))}"
staging_root = "{_toml_escape(str(runtime_root / "staging"))}"
state_root = "{_toml_escape(str(runtime_root / "state"))}"
runs_root = "{_toml_escape(str(runtime_root / "runs"))}"
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


def _default_data_root() -> Path:
    env_value = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return (Path.home() / ".obsidian" / "llm_wiki").resolve()


def _default_runtime_root(project_root: Path) -> Path:
    env_value = os.environ.get("TELLME_RUNTIME_ROOT", "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    base = (Path.home() / ".tmp" / "tellme").resolve()
    slug = project_root.resolve().as_posix().strip("/").replace("/", "-") or "tellme"
    return (base / slug).resolve()


def _data_paths(project_root: Path, machine: str) -> dict[str, Path]:
    machine_path = project_root / "config" / "machines" / f"{machine}.toml"
    if machine_path.exists():
        payload = _read_toml(machine_path)
        paths = payload.get("paths", {})
        if isinstance(paths, dict):
            return {
                "primary_wiki": Path(
                    str(paths.get("primary_wiki", paths.get("primary_vault", _default_data_root() / "wiki")))
                ).expanduser().resolve(),
                "raw_root": Path(str(paths.get("raw_root", _default_data_root() / "raw"))).expanduser().resolve(),
                "staging_root": Path(
                    str(paths.get("staging_root", _default_runtime_root(project_root) / "staging"))
                ).expanduser().resolve(),
                "state_root": Path(
                    str(paths.get("state_root", _default_runtime_root(project_root) / "state"))
                ).expanduser().resolve(),
                "runs_root": Path(
                    str(paths.get("runs_root", _default_runtime_root(project_root) / "runs"))
                ).expanduser().resolve(),
            }
    data_root = _default_data_root()
    runtime_root = _default_runtime_root(project_root)
    return {
        "primary_wiki": data_root / "wiki",
        "raw_root": data_root / "raw",
        "staging_root": runtime_root / "staging",
        "state_root": runtime_root / "state",
        "runs_root": runtime_root / "runs",
    }


def _read_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)
