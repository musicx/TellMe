from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectRuntime
from .files import atomic_write_json
from .hosts import HostResult, HostTask, HostValidationError
from .markdown import parse_frontmatter
from .state import ContentStatus, PageRecord, ProjectState, SourceRecord


class CodexResultError(RuntimeError):
    """Raised when Codex output cannot be safely consumed by TellMe."""


@dataclass(frozen=True)
class CodexHandoffResult:
    task_json_path: str
    task_markdown_path: str
    result_template_path: str
    source_references: list[str]


@dataclass(frozen=True)
class CodexConsumeResult:
    staged_page: str
    source_references: list[str]


def create_codex_handoff(runtime: ProjectRuntime, run_id: str) -> CodexHandoffResult:
    state = ProjectState.load(runtime.state_dir)
    source_references = sorted(
        SourceRecord.from_dict(payload).path for payload in state.sources().values()
    )
    task = HostTask(
        command="compile",
        run_id=run_id,
        host="codex",
        allowed_read_roots=["raw", "state", "vault"],
        allowed_write_roots=["staging", "runs"],
        inputs=source_references,
        expected_output=f"runs/{run_id}/artifacts/codex-result.json",
    )
    task_json = task.write(runtime.runs_dir / run_id / "host-tasks")
    task_markdown = task_json.with_suffix(".md")
    task_markdown.write_text(_task_markdown(task, source_references), encoding="utf-8")

    result_template = runtime.runs_dir / run_id / "artifacts" / "codex-result.template.json"
    atomic_write_json(
        result_template,
        {
            "schema_version": 1,
            "status": "succeeded",
            "host": "codex",
            "run_id": run_id,
            "output_path": f"staging/codex/{run_id}.md",
            "source_references": source_references,
            "confidence": "review-required",
            "errors": [],
        },
    )

    return CodexHandoffResult(
        task_json_path=_relative(runtime.project_root, task_json),
        task_markdown_path=_relative(runtime.project_root, task_markdown),
        result_template_path=_relative(runtime.project_root, result_template),
        source_references=source_references,
    )


def consume_codex_result(
    runtime: ProjectRuntime,
    result_path: Path,
    consume_run_id: str,
) -> CodexConsumeResult:
    try:
        result = HostResult.load(result_path)
    except (HostValidationError, KeyError, json.JSONDecodeError, OSError) as exc:
        raise CodexResultError(str(exc)) from exc

    if result.host != "codex":
        raise CodexResultError(f"expected codex result, got {result.host}")
    if result.status != "succeeded":
        raise CodexResultError(f"codex result status is not succeeded: {result.status}")

    output_path = (runtime.project_root / result.output_path).resolve()
    try:
        output_path.relative_to(runtime.staging_dir.resolve())
    except ValueError as exc:
        raise CodexResultError("codex output_path must be under staging/") from exc
    if not output_path.is_file():
        raise CodexResultError(f"codex output file not found: {result.output_path}")

    rel = _relative(runtime.project_root, output_path)
    frontmatter, _body = parse_frontmatter(output_path.read_text(encoding="utf-8"))
    page_type = str(frontmatter.get("page_type", "codex_candidate")) if frontmatter else "codex_candidate"
    state = ProjectState.load(runtime.state_dir)
    state.upsert_page(
        PageRecord(
            path=rel,
            page_type=page_type,
            status=ContentStatus.STAGED,
            sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(),
            sources=result.source_references,
            last_host="codex",
            last_run_id=consume_run_id,
            staged_path=rel,
        )
    )
    return CodexConsumeResult(staged_page=rel, source_references=result.source_references)


def _task_markdown(task: HostTask, source_references: list[str]) -> str:
    sources = "\n".join(f"- `{source}`" for source in source_references) or "- No registered sources."
    return f"""# TellMe Codex Compile Task

Run id: `{task.run_id}`
Command: `{task.command}`
Host: `codex`

## Goal

Create a reviewed Markdown candidate from the registered TellMe sources. Write your draft under `staging/codex/`, then write a result JSON artifact at `{task.expected_output}`.

## Allowed Read Roots

- `raw/`
- `state/`
- `vault/`

## Allowed Write Roots

- `staging/`
- `runs/`

Do not modify `raw/`.
Do not publish directly to `vault/`.

## Input Sources

{sources}

## Required Result JSON

Use the template at `runs/{task.run_id}/artifacts/codex-result.template.json`.
The final result JSON must include `schema_version`, `status`, `host`, `run_id`, `output_path`, and `source_references`.
"""


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
