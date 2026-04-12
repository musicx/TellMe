from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .resolver import resolve_project_root


@dataclass(frozen=True)
class ProjectSettings:
    name: str
    mode: str
    primary_wiki: str

    @property
    def primary_vault(self) -> str:
        return self.primary_wiki


@dataclass(frozen=True)
class MachineSettings:
    name: str
    platform: str
    paths: dict[str, Path]


@dataclass(frozen=True)
class HostSettings:
    name: str
    preferred_model: str
    command_profile: str


@dataclass(frozen=True)
class ProjectRuntime:
    project_root: Path
    data_root: Path
    project: ProjectSettings
    machine: MachineSettings | None
    host: HostSettings | None
    policies: dict[str, dict[str, Any]]
    raw_dir: Path
    staging_dir: Path
    state_dir: Path
    runs_dir: Path
    wiki_dir: Path

    @property
    def vault_dir(self) -> Path:
        return self.wiki_dir


def load_runtime(
    project_root: Path | None = None,
    machine: str | None = None,
    host: str | None = None,
) -> ProjectRuntime:
    root = resolve_project_root(explicit=project_root) if project_root else resolve_project_root()
    project_payload = _read_toml(root / "config" / "project.toml")
    project = _project_settings(project_payload)
    machine_settings = _load_machine(root, machine)
    host_settings = _load_host(root, host)
    policies = _load_policies(root)

    layout = dict(project_payload.get("layout", {}))
    data_root = _machine_data_root(machine_settings) or _data_root(project_payload)

    def path_for(key: str, default: str) -> Path:
        machine_key = f"{key}_root"
        if machine_settings and machine_key in machine_settings.paths:
            return machine_settings.paths[machine_key]
        if key == "wiki" and machine_settings:
            for legacy_key in ("primary_wiki", "primary_vault"):
                if legacy_key in machine_settings.paths:
                    return machine_settings.paths[legacy_key]
        return (data_root / str(layout.get(f"{key}_dir", default))).resolve()

    return ProjectRuntime(
        project_root=root,
        data_root=data_root,
        project=project,
        machine=machine_settings,
        host=host_settings,
        policies=policies,
        raw_dir=path_for("raw", "raw"),
        staging_dir=path_for("staging", "staging"),
        state_dir=path_for("state", "state"),
        runs_dir=path_for("runs", "runs"),
        wiki_dir=path_for("wiki", "wiki"),
    )


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _project_settings(payload: dict[str, Any]) -> ProjectSettings:
    project = payload.get("project", {})
    return ProjectSettings(
        name=str(project.get("name", "TellMe")),
        mode=str(project.get("mode", "hybrid-orchestrator")),
        primary_wiki=str(project.get("primary_wiki", project.get("primary_vault", "primary_wiki"))),
    )


def _data_root(payload: dict[str, Any]) -> Path:
    data = payload.get("data", {})
    env_var = str(data.get("root_env", "OBSIDIAN_VAULT_PATH"))
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    configured = str(data.get("root", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    fallback = str(data.get("fallback_root", "~/.obsidian/llm_wiki"))
    return Path(fallback).expanduser().resolve()


def _load_machine(root: Path, machine: str | None) -> MachineSettings | None:
    if not machine:
        return None
    machine_path = root / "config" / "machines" / f"{machine}.toml"
    if not machine_path.exists():
        return None

    payload = _read_toml(machine_path)
    machine_payload = payload.get("machine", {})
    paths_payload = payload.get("paths", {})
    return MachineSettings(
        name=str(machine_payload.get("name", machine)),
        platform=str(machine_payload.get("platform", "")),
        paths={key: Path(str(value)).expanduser().resolve() for key, value in paths_payload.items()},
    )


def _machine_data_root(machine_settings: MachineSettings | None) -> Path | None:
    if not machine_settings:
        return None
    for key in (
        "raw_root",
        "staging_root",
        "state_root",
        "runs_root",
        "wiki_root",
        "primary_wiki",
        "vault_root",
        "primary_vault",
    ):
        if key in machine_settings.paths:
            return machine_settings.paths[key].parent.resolve()
    return None


def _load_host(root: Path, host: str | None) -> HostSettings | None:
    if not host:
        return None
    host_path = root / "config" / "hosts" / f"{host}.toml"
    if not host_path.exists():
        return HostSettings(name=host, preferred_model="host-default", command_profile="default")
    payload = _read_toml(host_path)
    host_payload = payload.get("host", {})
    return HostSettings(
        name=str(host_payload.get("name", host)),
        preferred_model=str(host_payload.get("preferred_model", "host-default")),
        command_profile=str(host_payload.get("command_profile", "default")),
    )


def _load_policies(root: Path) -> dict[str, dict[str, Any]]:
    policies: dict[str, dict[str, Any]] = {
        "publish": {"source_summary_direct_publish": True},
        "lint": {"check_page_hash_drift": True, "check_running_runs": True},
    }
    policy_dir = root / "config" / "policies"
    if not policy_dir.exists():
        return policies
    for path in sorted(policy_dir.glob("*.toml")):
        payload = _read_toml(path)
        section = path.stem
        values = payload.get(section, payload)
        if isinstance(values, dict):
            policies.setdefault(section, {}).update(values)
    return policies
