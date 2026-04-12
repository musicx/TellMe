from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectRuntime
from .files import atomic_write_json
from .hosts import HostTask
from .state import ContentStatus, PageRecord, ProjectState, SourceRecord


@dataclass(frozen=True)
class CompileResult:
    published_pages: list[str]
    staged_pages: list[str]
    host_task_path: str
    artifact_path: str


def compile_sources(runtime: ProjectRuntime, run_id: str, host: str) -> CompileResult:
    state = ProjectState.load(runtime.state_dir)
    sources = [
        SourceRecord.from_dict(payload)
        for payload in state.sources().values()
        if ContentStatus(str(payload["status"])) in {ContentStatus.REGISTERED, ContentStatus.ANALYZED}
    ]
    published_pages: list[str] = []
    staged_pages: list[str] = []
    direct_publish = bool(
        runtime.policies.get("publish", {}).get("source_summary_direct_publish", True)
    )

    task = HostTask(
        command="compile",
        run_id=run_id,
        host=host,
        allowed_read_roots=["raw", "state", "wiki"],
        allowed_write_roots=["staging", "runs"],
        inputs=[source.path for source in sources],
        expected_output="artifacts/compile-result.json",
    )
    task_path = task.write(runtime.runs_dir / run_id / "host-tasks")

    for source in sources:
        raw_path = runtime.resolve_path(source.raw_path or source.path)
        if not raw_path.is_file():
            continue
        base_dir = runtime.wiki_dir if direct_publish else runtime.staging_dir
        page_path = base_dir / "sources" / f"{_slug(raw_path.stem)}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        content = _source_summary_page(
            title=raw_path.stem,
            source_path=source.path,
            source_text=raw_path.read_text(encoding="utf-8"),
            host=host,
            run_id=run_id,
            status="published" if direct_publish else "staged",
        )
        page_path.write_text(content, encoding="utf-8")
        page_rel = runtime.relativize_path(page_path)
        page_hash = hashlib.sha256(page_path.read_bytes()).hexdigest()
        state.upsert_page(
            PageRecord(
                path=page_rel,
                page_type="source_summary",
                status=ContentStatus.PUBLISHED if direct_publish else ContentStatus.STAGED,
                sha256=page_hash,
                sources=[source.path],
                last_host=host,
                last_run_id=run_id,
                published_path=page_rel if direct_publish else None,
                staged_path=page_rel if not direct_publish else None,
            )
        )
        state.upsert_source(
            SourceRecord(
                path=source.path,
                sha256=source.sha256,
                status=ContentStatus.ANALYZED,
                registered_at=source.registered_at,
                source_type=source.source_type,
                raw_path=source.raw_path,
                original_path=source.original_path,
                registration_run_id=source.registration_run_id,
            )
        )
        if direct_publish:
            published_pages.append(page_rel)
        else:
            staged_pages.append(page_rel)

    artifact_path = runtime.runs_dir / run_id / "artifacts" / "compile-result.json"
    atomic_write_json(
        artifact_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "host": host,
            "published_pages": published_pages,
            "staged_pages": staged_pages,
        },
    )

    return CompileResult(
        published_pages=published_pages,
        staged_pages=staged_pages,
        host_task_path=runtime.relativize_path(task_path),
        artifact_path=runtime.relativize_path(artifact_path),
    )


def _source_summary_page(
    title: str,
    source_path: str,
    source_text: str,
    host: str,
    run_id: str,
    status: str,
) -> str:
    excerpt = source_text.strip()[:4000]
    return (
        "---\n"
        "page_type: source_summary\n"
        f"status: {status}\n"
        f"sources:\n  - {source_path}\n"
        f"created_at: {_utc_now()}\n"
        f"updated_at: {_utc_now()}\n"
        f"last_host: {host}\n"
        f"last_run_id: {run_id}\n"
        "---\n"
        f"# {title}\n\n"
        "## Source\n\n"
        f"- `{source_path}`\n\n"
        "## Excerpt\n\n"
        "```markdown\n"
        f"{excerpt}\n"
        "```\n"
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "source"

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
