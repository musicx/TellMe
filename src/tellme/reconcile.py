from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import ProjectRuntime
from .state import ContentStatus, PageRecord, ProjectState


@dataclass(frozen=True)
class ReconcileResult:
    changed_pages: list[str]


def reconcile_vault(runtime: ProjectRuntime, run_id: str, host: str) -> ReconcileResult:
    state = ProjectState.load(runtime.state_dir)
    changed: list[str] = []

    for path, payload in state.pages().items():
        page = PageRecord.from_dict(payload)
        file_path = runtime.resolve_path(page.path)
        if not file_path.is_file():
            continue
        current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if current_hash == page.sha256:
            continue
        state.upsert_page(
            PageRecord(
                path=page.path,
                page_type=page.page_type,
                status=ContentStatus.RECONCILED,
                sha256=current_hash,
                sources=page.sources,
                last_host=host,
                last_run_id=run_id,
                published_path=page.published_path,
                staged_path=page.staged_path,
            )
        )
        changed.append(page.path)

    return ReconcileResult(changed_pages=changed)
