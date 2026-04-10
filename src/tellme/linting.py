from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json

from .config import ProjectRuntime
from .markdown import extract_wikilinks, parse_frontmatter
from .runs import RunRecord, RunStatus
from .state import PageRecord, ProjectState


@dataclass(frozen=True)
class LintIssue:
    issue_type: str
    path: str
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class LintResult:
    issues: list[LintIssue]

    @property
    def ok(self) -> bool:
        return not self.issues


def lint_vault(runtime: ProjectRuntime, current_run_id: str | None = None) -> LintResult:
    pages = sorted(runtime.vault_dir.rglob("*.md"))
    titles = {page.stem for page in pages}
    issues: list[LintIssue] = []

    for page in pages:
        rel = _relative(runtime.project_root, page)
        text = page.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(text)
        if not frontmatter:
            issues.append(LintIssue("missing_frontmatter", rel, "Page has no frontmatter"))
        elif "sources" not in frontmatter:
            issues.append(LintIssue("missing_sources", rel, "Page frontmatter has no sources"))

        for link in extract_wikilinks(body):
            if link not in titles:
                issues.append(LintIssue("broken_link", rel, f"Broken wikilink: [[{link}]]"))

    if runtime.policies.get("lint", {}).get("check_page_hash_drift", True):
        state = ProjectState.load(runtime.state_dir)
        for payload in state.pages().values():
            record = PageRecord.from_dict(payload)
            path = runtime.project_root / record.path
            if not path.is_file():
                continue
            current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if current_hash != record.sha256:
                issues.append(
                    LintIssue(
                        "page_hash_drift",
                        record.path,
                        "Known page hash differs from state; run tellme reconcile if this is intentional.",
                    )
                )

    if runtime.policies.get("lint", {}).get("check_running_runs", True):
        for run_json in sorted(runtime.runs_dir.glob("*/run.json")):
            payload = json.loads(run_json.read_text(encoding="utf-8"))
            run = RunRecord.from_dict(payload)
            if current_run_id and run.run_id == current_run_id:
                continue
            if run.status == RunStatus.RUNNING:
                issues.append(
                    LintIssue(
                        "running_run",
                        _relative(runtime.project_root, run_json),
                        "Run is still marked running; inspect diagnostics or rerun the workflow.",
                    )
                )

    return LintResult(issues=issues)


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
