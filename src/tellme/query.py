from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectRuntime
from .hosts import HostTask
from .state import ContentStatus, PageRecord, ProjectState


@dataclass(frozen=True)
class QueryResult:
    answer_path: str
    matched_pages: list[str]
    host_task_path: str
    staged_path: str | None = None


def query_vault(
    runtime: ProjectRuntime,
    question: str,
    run_id: str,
    host: str,
    stage: bool = False,
) -> QueryResult:
    matches = _match_pages(runtime, question)
    task = HostTask(
        command="query",
        run_id=run_id,
        host=host,
        allowed_read_roots=["vault", "state"],
        allowed_write_roots=["staging", "runs"],
        inputs=[path for path, _score in matches],
        expected_output="artifacts/query-answer.md",
    )
    task_path = task.write(runtime.runs_dir / run_id / "host-tasks")
    answer = _answer_markdown(question=question, host=host, run_id=run_id, matched_pages=matches)
    artifact_path = runtime.runs_dir / run_id / "artifacts" / "query-answer.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(answer, encoding="utf-8")

    staged_path: Path | None = None
    if stage and matches:
        slug = _slug(question)
        staged_path = runtime.staging_dir / "synthesis" / f"{slug}.md"
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        matched_paths = [path for path, _score in matches]
        staged_path.write_text(
            _staged_synthesis_markdown(
                answer=answer,
                question=question,
                sources=matched_paths,
                host=host,
                run_id=run_id,
            ),
            encoding="utf-8",
        )
        rel = _relative(runtime.data_root, staged_path)
        state = ProjectState.load(runtime.state_dir)
        state.upsert_page(
            PageRecord(
                path=rel,
                page_type="synthesis",
                status=ContentStatus.STAGED,
                sha256=hashlib.sha256(staged_path.read_bytes()).hexdigest(),
                sources=matched_paths,
                last_host=host,
                last_run_id=run_id,
                staged_path=rel,
            )
        )
        state.upsert_synthesis(
            {
                "id": f"synthesis:{slug}",
                "title": question,
                "question": question,
                "status": ContentStatus.STAGED.value,
                "sources": matched_paths,
                "staged_path": rel,
                "last_host": host,
                "last_run_id": run_id,
            }
        )

    return QueryResult(
        answer_path=_relative(runtime.data_root, artifact_path),
        matched_pages=[path for path, _score in matches],
        host_task_path=_relative(runtime.data_root, task_path),
        staged_path=_relative(runtime.data_root, staged_path) if staged_path else None,
    )


def _match_pages(runtime: ProjectRuntime, question: str) -> list[tuple[str, int]]:
    terms = [term for term in re.findall(r"[A-Za-z0-9_]+", question.lower()) if len(term) > 2]
    scored: list[tuple[str, int]] = []
    for page in sorted(runtime.vault_dir.rglob("*.md")):
        text = page.read_text(encoding="utf-8", errors="replace").lower()
        score = sum(text.count(term) for term in terms)
        if score > 0:
            scored.append((_relative(runtime.data_root, page), score))
    return sorted(scored, key=lambda item: (-item[1], item[0]))[:10]


def _answer_markdown(
    question: str,
    host: str,
    run_id: str,
    matched_pages: list[tuple[str, int]],
) -> str:
    lines = [
        "# Query Answer",
        "",
        f"Question: {question}",
        "",
        f"Host: {host}",
        f"Run: {run_id}",
        "",
        "This deterministic V1 does not call an LLM. It reads published vault pages first and records the matching context for a host or human follow-up.",
        "",
        "## Matched Published Pages",
        "",
    ]
    if not matched_pages:
        lines.append("- No matching published pages found.")
    else:
        for path, score in matched_pages:
            lines.append(f"- `{path}` (score: {score})")
    lines.append("")
    return "\n".join(lines)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug[:80] or "query"


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _staged_synthesis_markdown(
    answer: str,
    question: str,
    sources: list[str],
    host: str,
    run_id: str,
) -> str:
    now = _utc_now()
    source_lines = "\n".join(f"  - {source}" for source in sources)
    return (
        "---\n"
        "page_type: synthesis\n"
        "status: staged\n"
        f"question: {question}\n"
        "sources:\n"
        f"{source_lines}\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"last_host: {host}\n"
        f"last_run_id: {run_id}\n"
        "---\n"
        "# Query Synthesis Candidate\n\n"
        f"{answer}"
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
