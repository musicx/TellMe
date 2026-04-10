from __future__ import annotations

from pathlib import Path


class ProjectNotFoundError(RuntimeError):
    """Raised when a TellMe project root cannot be resolved."""


def resolve_project_root(start: Path | None = None, explicit: Path | None = None) -> Path:
    if explicit is not None:
        root = explicit.expanduser().resolve()
        if _is_project_root(root):
            return root
        raise ProjectNotFoundError(f"{root} is not a TellMe project root")

    current = (start or Path.cwd()).expanduser().resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if _is_project_root(candidate):
            return candidate

    raise ProjectNotFoundError(
        f"{current} is not inside a TellMe project. Run `tellme init` or pass `--project`."
    )


def _is_project_root(path: Path) -> bool:
    return (path / "config" / "project.toml").is_file()
