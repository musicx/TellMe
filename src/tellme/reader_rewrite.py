from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectRuntime
from .files import atomic_write_json
from .hosts import KNOWN_HOSTS, HostTask
from .state import ContentStatus, PageRecord, ProjectState


class ReaderRewriteError(RuntimeError):
    """Raised when a reader page rewrite cannot be safely processed."""


@dataclass(frozen=True)
class ReaderRewriteHandoffResult:
    task_json_path: str
    task_markdown_path: str
    result_template_path: str


@dataclass(frozen=True)
class ReaderRewriteConsumeResult:
    result_path: str
    staged_pages: list[str]


def create_reader_rewrite_handoff(runtime: ProjectRuntime, run_id: str, host: str) -> ReaderRewriteHandoffResult:
    state = ProjectState.load(runtime.state_dir)
    reader_pages = sorted(
        {"vault/index.md"}
        | {
        page_path
        for page_path, payload in state.pages().items()
        if payload.get("status") == ContentStatus.PUBLISHED.value
        and str(payload.get("page_type")) in {"overview", "theme", "subtheme", "reference"}
        and page_path.startswith("vault/")
        }
    )
    task = HostTask(
        command="reader-rewrite",
        run_id=run_id,
        host=host,
        allowed_read_roots=["raw", "state", "vault", "staging"],
        allowed_write_roots=["staging", "runs"],
        inputs=reader_pages,
        expected_output=f"staging/reader-rewrite/{run_id}.json",
    )
    task_json = task.write(runtime.runs_dir / run_id / "host-tasks")
    task_markdown = task_json.with_suffix(".md")
    task_markdown.write_text(_task_markdown(task, reader_pages), encoding="utf-8")

    result_template = runtime.runs_dir / run_id / "artifacts" / "reader-rewrite.template.json"
    atomic_write_json(
        result_template,
        {
            "schema_version": 1,
            "candidate_type": "reader_page_rewrites",
            "run_id": run_id,
            "host": host,
            "rewrites": [],
        },
    )
    return ReaderRewriteHandoffResult(
        task_json_path=_relative(runtime.data_root, task_json),
        task_markdown_path=_relative(runtime.data_root, task_markdown),
        result_template_path=_relative(runtime.data_root, result_template),
    )


def consume_reader_rewrite_result(
    runtime: ProjectRuntime,
    result_path: Path,
    consume_run_id: str,
) -> ReaderRewriteConsumeResult:
    resolved = result_path.resolve()
    try:
        resolved.relative_to(runtime.staging_dir.resolve())
    except ValueError as exc:
        raise ReaderRewriteError("reader rewrite result path must be under staging/") from exc
    if not resolved.is_file():
        raise ReaderRewriteError(f"reader rewrite result file not found: {_relative(runtime.data_root, resolved)}")

    payload = _load_result(resolved)
    state = ProjectState.load(runtime.state_dir)
    staged_pages: list[str] = []

    for rewrite in payload["rewrites"]:
        target_path = str(rewrite["target_path"])
        page_type = str(rewrite["page_type"])
        sources = [str(source) for source in rewrite["sources"]]
        target = runtime.data_root / target_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(rewrite["content"]), encoding="utf-8")
        rel = _relative(runtime.data_root, target)
        state.upsert_page(
            PageRecord(
                path=rel,
                page_type=page_type,
                status=ContentStatus.STAGED,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                sources=sources,
                last_host=str(payload["host"]),
                last_run_id=consume_run_id,
                staged_path=rel,
            )
        )
        staged_pages.append(rel)

    return ReaderRewriteConsumeResult(
        result_path=_relative(runtime.data_root, resolved),
        staged_pages=staged_pages,
    )


def _load_result(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ReaderRewriteError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ReaderRewriteError("reader rewrite result must be a JSON object")
    if int(payload.get("schema_version", 0)) != 1:
        raise ReaderRewriteError("unsupported reader rewrite schema_version")
    if payload.get("candidate_type") != "reader_page_rewrites":
        raise ReaderRewriteError("candidate_type must be reader_page_rewrites")
    host = str(payload.get("host", ""))
    if host not in KNOWN_HOSTS:
        raise ReaderRewriteError(f"unknown host: {host}")
    rewrites = payload.get("rewrites")
    if not isinstance(rewrites, list):
        raise ReaderRewriteError("rewrites must be a list")
    for rewrite in rewrites:
        if not isinstance(rewrite, dict):
            raise ReaderRewriteError("rewrites must contain objects")
        page_type = str(rewrite.get("page_type", "")).strip()
        if page_type not in {"overview", "theme", "subtheme", "reference"}:
            raise ReaderRewriteError("reader rewrite page_type must be overview, theme, subtheme, or reference")
        target_path = str(rewrite.get("target_path", "")).strip()
        if not target_path.startswith("staging/reader-rewrite/"):
            raise ReaderRewriteError("reader rewrite target_path must be under staging/reader-rewrite/")
        sources = rewrite.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ReaderRewriteError("reader rewrite must include sources")
        if not str(rewrite.get("content", "")).strip():
            raise ReaderRewriteError("reader rewrite must include content")
    return payload


def _task_markdown(task: HostTask, reader_pages: list[str]) -> str:
    pages = "\n".join(f"- `{page}`" for page in reader_pages) or "- No reader-facing pages yet."
    return f"""# TellMe Reader Rewrite Task

Run id: `{task.run_id}`
Host: `{task.host}`

## Goal

Rewrite existing reader-facing pages so they read more naturally while preserving source traceability and page role boundaries.

## Allowed Read Roots

- `raw/`
- `state/`
- `vault/`
- `staging/`

## Allowed Write Roots

- `staging/`
- `runs/`

Do not modify `raw/`.
Do not write directly to `vault/`.

## Reader-Facing Pages In Scope

{pages}

## Required Result JSON

Use the template at `runs/{task.run_id}/artifacts/reader-rewrite.template.json`.

Each rewrite entry must include:

- `page_type`
- `target_path`
- `sources`
- `content`
"""


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
