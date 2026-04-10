from __future__ import annotations

import hashlib
from pathlib import Path

from tellme.config import load_runtime
from tellme.project import init_project
from tellme.reconcile import reconcile_vault
from tellme.state import ContentStatus, PageRecord, ProjectState


def test_reconcile_updates_state_for_modified_published_page_without_overwrite(tmp_path: Path) -> None:
    project_root = tmp_path / "TellMe"
    init_project(project_root, machine="test-pc")
    page_path = project_root / "vault" / "Page.md"
    page_path.write_text("---\ntitle: Page\nsources: [raw/page.md]\n---\nOriginal", encoding="utf-8")
    state = ProjectState.load(project_root / "state")
    state.upsert_page(
        PageRecord(
            path="vault/Page.md",
            page_type="concept",
            status=ContentStatus.PUBLISHED,
            sha256="old-hash",
            sources=["raw/page.md"],
            last_host="codex",
            last_run_id="previous-run",
        )
    )
    page_path.write_text("---\ntitle: Page\nsources: [raw/page.md]\n---\nHuman edit", encoding="utf-8")
    runtime = load_runtime(project_root=project_root, machine="test-pc")

    result = reconcile_vault(runtime=runtime, run_id="reconcile-run", host="codex")

    assert result.changed_pages == ["vault/Page.md"]
    assert page_path.read_text(encoding="utf-8").endswith("Human edit")
    updated = ProjectState.load(project_root / "state").get_page("vault/Page.md")
    assert updated.status == ContentStatus.RECONCILED
    assert updated.sha256 == hashlib.sha256(page_path.read_bytes()).hexdigest()
    assert updated.last_run_id == "reconcile-run"
