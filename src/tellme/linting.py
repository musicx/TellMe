from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import ProjectRuntime
from .markdown import extract_wikilinks, parse_frontmatter


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


def lint_vault(runtime: ProjectRuntime) -> LintResult:
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

    return LintResult(issues=issues)


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
