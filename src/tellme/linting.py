from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re

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
    pages = sorted(runtime.wiki_dir.rglob("*.md"))
    issues: list[LintIssue] = []
    titles: set[str] = set()

    page_cache: list[tuple[Path, str, dict, str]] = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(text)
        page_cache.append((page, text, frontmatter, body))
        titles.update(_page_titles(page, frontmatter, body))

    for page, text, frontmatter, body in page_cache:
        rel = runtime.relativize_path(page)
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
            path = runtime.resolve_path(record.path)
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
        node_ids = set(state.nodes())
        for relation in state.relations().values():
            source = str(relation.get("source", ""))
            target = str(relation.get("target", ""))
            if source and source not in node_ids:
                issues.append(
                    LintIssue(
                        "graph_broken_relation",
                        str(relation.get("id", source)),
                        f"Graph relation source node is missing: {source}",
                    )
                )
            if target and target not in node_ids:
                issues.append(
                    LintIssue(
                        "graph_broken_relation",
                        str(relation.get("id", target)),
                        f"Graph relation target node is missing: {target}",
                    )
                )
        known_ids = (
            set(state.nodes())
            | set(state.claims())
            | set(state.relations())
            | set(state.conflicts())
            | set(state.syntheses())
            | set(state.outputs())
        )
        for finding in state.health_findings().values():
            staged_path = str(finding.get("staged_path", ""))
            if staged_path and not runtime.resolve_path(staged_path).is_file():
                issues.append(
                    LintIssue(
                        "health_missing_staged_page",
                        staged_path,
                        "Tracked health finding review page is missing from staging.",
                    )
                )
            for affected_id in finding.get("affected_ids", []):
                affected_value = str(affected_id)
                if affected_value and affected_value not in known_ids:
                    issues.append(
                        LintIssue(
                            "health_unknown_affected_id",
                            str(finding.get("id", staged_path or affected_value)),
                            f"Health finding affected id is missing from state: {affected_value}",
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
                        runtime.relativize_path(run_json),
                        "Run is still marked running; inspect diagnostics or rerun the workflow.",
                    )
                )

    return LintResult(issues=issues)

def _page_titles(page: Path, frontmatter: dict, body: str) -> set[str]:
    titles = {page.stem}
    title = str(frontmatter.get("title", "")).strip()
    if title:
        titles.add(title)
    heading_match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    if heading_match:
        titles.add(heading_match.group(1).strip())
    return {title for title in titles if title}
