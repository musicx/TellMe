from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectRuntime
from .state import ContentStatus, PageRecord, ProjectState


class PublishError(RuntimeError):
    """Raised when a staged graph page cannot be safely published."""


@dataclass(frozen=True)
class PublishResult:
    published_pages: list[str]


def publish_staged_graph(
    runtime: ProjectRuntime,
    run_id: str,
    host: str,
    staged_path: str | None = None,
) -> PublishResult:
    state = ProjectState.load(runtime.state_dir)
    records = _select_staged_graph_pages(state, staged_path=staged_path)
    published_pages: list[str] = []

    for page in records:
        source_path = runtime.data_root / page.path
        if not source_path.is_file():
            raise PublishError(f"staged page not found: {page.path}")
        vault_rel = _vault_path_for(page.path)
        vault_path = runtime.data_root / vault_rel
        vault_path.parent.mkdir(parents=True, exist_ok=True)
        vault_path.write_text(
            _publish_page_text(source_path.read_text(encoding="utf-8"), host=host, run_id=run_id),
            encoding="utf-8",
        )
        page_hash = hashlib.sha256(vault_path.read_bytes()).hexdigest()
        state.upsert_page(
            PageRecord(
                path=page.path,
                page_type=page.page_type,
                status=ContentStatus.PUBLISHED,
                sha256=page.sha256,
                sources=page.sources,
                last_host=host,
                last_run_id=run_id,
                published_path=vault_rel,
                staged_path=page.path,
            )
        )
        state.upsert_page(
            PageRecord(
                path=vault_rel,
                page_type=page.page_type,
                status=ContentStatus.PUBLISHED,
                sha256=page_hash,
                sources=page.sources,
                last_host=host,
                last_run_id=run_id,
                published_path=vault_rel,
                staged_path=page.path,
            )
        )
        _mark_node_published(
            state=state,
            staged_path=page.path,
            published_path=vault_rel,
            host=host,
            run_id=run_id,
        )
        published_pages.append(vault_rel)

    return PublishResult(published_pages=published_pages)


def _select_staged_graph_pages(state: ProjectState, staged_path: str | None) -> list[PageRecord]:
    pages = [PageRecord.from_dict(payload) for payload in state.pages().values()]
    if staged_path is not None:
        if not staged_path.startswith("staging/"):
            raise PublishError("publish target must be under staging/")
        pages = [page for page in pages if page.path == staged_path]
        if not pages:
            raise PublishError(f"staged page is not tracked: {staged_path}")
    return sorted(
        [
            page
            for page in pages
            if page.status == ContentStatus.STAGED
            and page.page_type in {"concept", "entity"}
            and page.path.startswith(("staging/concepts/", "staging/entities/"))
        ],
        key=lambda page: page.path,
    )


def _vault_path_for(staged_path: str) -> str:
    if not staged_path.startswith("staging/"):
        raise PublishError("publish target must be under staging/")
    return "vault/" + staged_path.removeprefix("staging/")


def _publish_page_text(text: str, host: str, run_id: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    replacements = {
        "status": "published",
        "updated_at": now,
        "last_host": host,
        "last_run_id": run_id,
    }
    for key, value in replacements.items():
        text = _replace_frontmatter_scalar(text, key, value)
    return text


def _replace_frontmatter_scalar(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^({re.escape(key)}:\s*).*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(rf"\g<1>{value}", text, count=1)
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end == -1:
        return text
    return text[:end] + f"\n{key}: {value}" + text[end:]


def _mark_node_published(
    state: ProjectState,
    staged_path: str,
    published_path: str,
    host: str,
    run_id: str,
) -> None:
    for node in state.nodes().values():
        if node.get("staged_path") != staged_path:
            continue
        updated = dict(node)
        updated["status"] = ContentStatus.PUBLISHED.value
        updated["published_path"] = published_path
        updated["last_host"] = host
        updated["last_run_id"] = run_id
        state.upsert_node(updated)
