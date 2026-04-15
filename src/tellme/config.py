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
    runtime_root: Path
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

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path.resolve()
        normalized = str(path).replace("\\", "/")
        if normalized == "raw" or normalized.startswith("raw/"):
            suffix = normalized.removeprefix("raw").lstrip("/")
            return (self.raw_dir / suffix).resolve()
        if normalized == "wiki" or normalized.startswith("wiki/"):
            suffix = normalized.removeprefix("wiki").lstrip("/")
            return (self.wiki_dir / suffix).resolve()
        if normalized == "staging" or normalized.startswith("staging/"):
            suffix = normalized.removeprefix("staging").lstrip("/")
            return (self.staging_dir / suffix).resolve()
        if normalized == "state" or normalized.startswith("state/"):
            suffix = normalized.removeprefix("state").lstrip("/")
            return (self.state_dir / suffix).resolve()
        if normalized == "runs" or normalized.startswith("runs/"):
            suffix = normalized.removeprefix("runs").lstrip("/")
            return (self.runs_dir / suffix).resolve()
        return (self.project_root / path).resolve()

    def relativize_path(self, path: Path) -> str:
        resolved = path.resolve()
        for prefix, root in (
            ("raw", self.raw_dir),
            ("wiki", self.wiki_dir),
            ("staging", self.staging_dir),
            ("state", self.state_dir),
            ("runs", self.runs_dir),
        ):
            try:
                rel = resolved.relative_to(root.resolve()).as_posix()
                return prefix if not rel or rel == "." else f"{prefix}/{rel}"
            except ValueError:
                continue
        try:
            return resolved.relative_to(self.project_root.resolve()).as_posix()
        except ValueError:
            return resolved.as_posix()


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
    data_root = _content_root(project_payload, machine_settings)
    runtime_root = _runtime_root(project_payload, root, machine_settings)

    def path_for(key: str, default: str, *, root_path: Path) -> Path:
        machine_key = f"{key}_root"
        if machine_settings and machine_key in machine_settings.paths:
            return machine_settings.paths[machine_key]
        if key == "wiki" and machine_settings:
            for legacy_key in ("primary_wiki", "primary_vault"):
                if legacy_key in machine_settings.paths:
                    return machine_settings.paths[legacy_key]
        return (root_path / str(layout.get(f"{key}_dir", default))).resolve()

    return ProjectRuntime(
        project_root=root,
        data_root=data_root,
        runtime_root=runtime_root,
        project=project,
        machine=machine_settings,
        host=host_settings,
        policies=policies,
        raw_dir=path_for("raw", "raw", root_path=data_root),
        staging_dir=path_for("staging", "staging", root_path=runtime_root),
        state_dir=path_for("state", "state", root_path=runtime_root),
        runs_dir=path_for("runs", "runs", root_path=runtime_root),
        wiki_dir=path_for("wiki", "wiki", root_path=data_root),
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


def _content_root(payload: dict[str, Any], machine_settings: MachineSettings | None) -> Path:
    if machine_settings:
        for key in ("raw_root", "wiki_root", "primary_wiki", "primary_vault", "vault_root"):
            if key in machine_settings.paths:
                return machine_settings.paths[key].parent.resolve()
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


def _runtime_root(
    payload: dict[str, Any],
    project_root: Path,
    machine_settings: MachineSettings | None,
) -> Path:
    if machine_settings:
        for key in ("state_root", "staging_root", "runs_root"):
            if key in machine_settings.paths:
                return machine_settings.paths[key].parent.resolve()
    data = payload.get("data", {})
    env_var = str(data.get("runtime_root_env", "TELLME_RUNTIME_ROOT"))
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    configured = str(data.get("runtime_root", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    fallback_root = Path(str(data.get("runtime_fallback_root", "~/.tmp/tellme"))).expanduser().resolve()
    slug = _path_slug(project_root.resolve())
    return (fallback_root / slug).resolve()


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


def _path_slug(path: Path) -> str:
    value = path.as_posix().strip("/")
    return value.replace("/", "-") or "tellme"
