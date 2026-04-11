from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectRuntime
from .state import ContentStatus, PageRecord, ProjectState


@dataclass(frozen=True)
class IndexResult:
    index_pages: list[str]


def generate_vault_indexes(runtime: ProjectRuntime, run_id: str, host: str) -> IndexResult:
    state = ProjectState.load(runtime.state_dir)
    pages = _reader_facing_pages(state) + [
        ("vault/indexes/concepts.md", _node_index("Concepts", "concept", state.nodes())),
        ("vault/indexes/entities.md", _node_index("Entities", "entity", state.nodes())),
        ("vault/indexes/synthesis.md", _synthesis_index(state.syntheses())),
        ("vault/indexes/unresolved-conflicts.md", _conflict_index(state.conflicts())),
        ("vault/indexes/health-review.md", _health_review_index(state.health_findings())),
    ]
    written: list[str] = []

    for rel, body in pages:
        path = runtime.data_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _page_markdown(
                title=_title_for(rel),
                body=body,
                host=host,
                run_id=run_id,
                page_type=_page_type_for(rel),
            ),
            encoding="utf-8",
        )
        state.upsert_page(
            PageRecord(
                path=rel,
                page_type=_page_type_for(rel),
                status=ContentStatus.PUBLISHED,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                sources=[],
                last_host=host,
                last_run_id=run_id,
                published_path=rel,
            )
        )
        state.upsert_index(
            {
                "id": rel,
                "path": rel,
                "title": _title_for(rel),
                "status": ContentStatus.PUBLISHED.value,
                "last_host": host,
                "last_run_id": run_id,
                "published_path": rel,
            }
        )
        written.append(rel)

    return IndexResult(index_pages=written)


def _reader_facing_pages(state: ProjectState) -> list[tuple[str, str]]:
    published_nodes = [
        node
        for node in state.nodes().values()
        if node.get("status") == ContentStatus.PUBLISHED.value
    ]
    themes = _group_themes(published_nodes)
    references = _reference_nodes(published_nodes)

    pages: list[tuple[str, str]] = [("vault/index.md", _overview_page(themes, references))]
    for theme_name, theme in sorted(themes.items()):
        pages.append((f"vault/{theme['path']}", _theme_page(theme_name, theme)))
        for subtheme_name, subtheme in sorted(theme["subthemes"].items()):
            pages.append((f"vault/{subtheme['path']}", _subtheme_page(theme_name, subtheme_name, subtheme)))
    for reference in references:
        if reference["path"]:
            pages.append((reference["path"], _reference_page(reference["node"], state)))
    return pages


def _group_themes(published_nodes: list[dict]) -> dict[str, dict]:
    themes: dict[str, dict] = {}
    for node in published_nodes:
        theme_name = str(node.get("theme", "")).strip()
        if not theme_name:
            continue
        theme_slug = _slug(theme_name)
        theme = themes.setdefault(
            theme_name,
            {
                "slug": theme_slug,
                "path": f"themes/{theme_slug}.md",
                "nodes": [],
                "subthemes": {},
            },
        )
        theme["nodes"].append(node)
        subtheme_name = str(node.get("subtheme", "")).strip()
        if subtheme_name:
            subtheme = theme["subthemes"].setdefault(
                subtheme_name,
                {
                    "slug": f"{theme_slug}-{_slug(subtheme_name)}",
                    "path": f"subthemes/{theme_slug}-{_slug(subtheme_name)}.md",
                    "nodes": [],
                },
            )
            subtheme["nodes"].append(node)
    return themes


def _reference_nodes(published_nodes: list[dict]) -> list[dict]:
    references: list[dict] = []
    for node in published_nodes:
        if str(node.get("reader_role", "reference")) != "reference":
            continue
        published_path = str(node.get("published_path", ""))
        if not published_path.startswith("vault/references/"):
            continue
        references.append(
            {
                "title": str(node.get("title", node.get("id", "Untitled"))),
                "link": _relative_link("vault/index.md", published_path),
                "path": published_path,
                "node": node,
            }
        )
    return sorted(references, key=lambda item: item["title"].lower())


def _overview_page(themes: dict[str, dict], references: list[dict]) -> str:
    lines = ["## Themes", ""]
    if not themes:
        lines.append("No reader-facing themes yet.")
    else:
        for theme_name, theme in sorted(themes.items()):
            lines.append(f"- [{theme_name}]({theme['path']})")
    lines.extend(["", "## Key References", ""])
    if not references:
        lines.append("No promoted reference pages yet.")
    else:
        for reference in references:
            lines.append(f"- [{reference['title']}]({reference['link']})")
    lines.extend(
        [
            "",
            "## Maintenance Surfaces",
            "",
            "- [Concepts](indexes/concepts.md)",
            "- [Entities](indexes/entities.md)",
            "- [Synthesis](indexes/synthesis.md)",
            "- [Unresolved Conflicts](indexes/unresolved-conflicts.md)",
            "- [Health Review](indexes/health-review.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def _theme_page(theme_name: str, theme: dict) -> str:
    lines = ["## Subthemes", ""]
    if not theme["subthemes"]:
        lines.append("No subthemes yet.")
    else:
        for subtheme_name, subtheme in sorted(theme["subthemes"].items()):
            lines.append(f"- [{subtheme_name}](../{subtheme['path']})")
    lines.extend(["", "## Key References", ""])
    reference_nodes = [
        node for node in theme["nodes"] if str(node.get("reader_role", "reference")) == "reference"
    ]
    if not reference_nodes:
        lines.append("No promoted references yet.")
    else:
        for node in sorted(reference_nodes, key=lambda item: str(item.get("title", "")).lower()):
            lines.append(
                f"- [{node['title']}](../references/{_slug(Path(str(node.get('published_path', node['id']))).stem)}.md)"
            )
    lines.extend(["", "## Coverage", ""])
    for node in sorted(theme["nodes"], key=lambda item: str(item.get("title", "")).lower()):
        lines.append(f"### {node['title']}")
        lines.append("")
        lines.append(str(node.get("summary", "No summary available.")))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _subtheme_page(theme_name: str, subtheme_name: str, subtheme: dict) -> str:
    lines = [
        "## Parent Theme",
        "",
        f"- [{theme_name}](../themes/{_slug(theme_name)}.md)",
        "",
        "## Covered Knowledge",
        "",
    ]
    for node in sorted(subtheme["nodes"], key=lambda item: str(item.get("title", "")).lower()):
        lines.append(f"### {node['title']}")
        lines.append("")
        lines.append(str(node.get("summary", "No summary available.")))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _reference_page(node: dict, state: ProjectState) -> str:
    lines = ["## Summary", "", str(node.get("summary", "No summary available.")), "", "## Theme Placement", ""]
    theme = str(node.get("theme", "")).strip()
    subtheme = str(node.get("subtheme", "")).strip()
    if theme:
        lines.append(f"- Theme: [{theme}](../themes/{_slug(theme)}.md)")
    if subtheme:
        lines.append(f"- Subtheme: [{subtheme}](../subthemes/{_slug(theme)}-{_slug(subtheme)}.md)")
    if not theme and not subtheme:
        lines.append("- No theme assignment yet.")
    lines.extend(["", "## Claims", ""])
    claims = [claim for claim in state.claims().values() if claim.get("subject") == node.get("id")]
    if not claims:
        lines.append("No claims yet.")
    else:
        for claim in claims:
            lines.append(f"- {claim['text']}")
    lines.extend(["", "## Sources", ""])
    for source in node.get("sources", []):
        lines.append(f"- `{source}`")
    return "\n".join(lines) + "\n"


def _node_index(title: str, kind: str, nodes: dict[str, dict]) -> str:
    lines = [f"## {title}", ""]
    matching = [
        node
        for node in nodes.values()
        if node.get("kind") == kind and node.get("status") == ContentStatus.PUBLISHED.value
    ]
    if not matching:
        lines.append(f"No published {title.lower()} yet.")
    for node in sorted(matching, key=lambda item: str(item.get("title", item.get("id", ""))).lower()):
        title_value = str(node.get("title", node.get("id", "Untitled")))
        path = str(node.get("published_path", ""))
        link = _relative_link(from_rel=f"vault/indexes/{kind}s.md", to_rel=path) if path else ""
        lines.append(f"- [{title_value}]({link})" if link else f"- {title_value}")
    return "\n".join(lines) + "\n"


def _synthesis_index(syntheses: dict[str, dict]) -> str:
    lines = ["## Synthesis", ""]
    published = [item for item in syntheses.values() if item.get("status") == ContentStatus.PUBLISHED.value]
    if not published:
        lines.append("No published synthesis pages yet.")
    for synthesis in sorted(published, key=lambda item: str(item.get("title", item.get("id", ""))).lower()):
        title = str(synthesis.get("title", synthesis.get("id", "Untitled")))
        path = str(synthesis.get("published_path", ""))
        link = _relative_link(from_rel="vault/indexes/synthesis.md", to_rel=path) if path else ""
        lines.append(f"- [{title}]({link})" if link else f"- {title}")
    return "\n".join(lines) + "\n"


def _conflict_index(conflicts: dict[str, dict]) -> str:
    lines = ["## Unresolved Conflicts", ""]
    unresolved = [
        item
        for item in conflicts.values()
        if item.get("status") != ContentStatus.PUBLISHED.value and item.get("status") != "resolved"
    ]
    if not unresolved:
        lines.append("No unresolved conflicts.")
    for conflict in sorted(unresolved, key=lambda item: str(item.get("summary", item.get("id", ""))).lower()):
        summary = str(conflict.get("summary", conflict.get("id", "Untitled conflict")))
        path = str(conflict.get("staged_path", conflict.get("published_path", "")))
        link = _relative_link(from_rel="vault/indexes/unresolved-conflicts.md", to_rel=path) if path else ""
        lines.append(f"- [{summary}]({link})" if link else f"- {summary}")
    return "\n".join(lines) + "\n"


def _health_review_index(health_findings: dict[str, dict]) -> str:
    lines = ["## Health Review", ""]
    staged = [item for item in health_findings.values() if item.get("status") == ContentStatus.STAGED.value]
    if not staged:
        lines.append("No staged health findings.")
    for finding in sorted(staged, key=lambda item: str(item.get("summary", item.get("id", ""))).lower()):
        summary = str(finding.get("summary", finding.get("id", "Untitled finding")))
        path = str(finding.get("staged_path", ""))
        link = _relative_link(from_rel="vault/indexes/health-review.md", to_rel=path) if path else ""
        lines.append(f"- [{summary}]({link})" if link else f"- {summary}")
    return "\n".join(lines) + "\n"


def _page_markdown(title: str, body: str, host: str, run_id: str, page_type: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return (
        "---\n"
        f"page_type: {page_type}\n"
        "status: published\n"
        "sources: []\n"
        f"created_at: {now}\n"
        f"updated_at: {now}\n"
        f"last_host: {host}\n"
        f"last_run_id: {run_id}\n"
        "---\n"
        f"# {title}\n\n"
        f"{body}"
    )


def _page_type_for(rel: str) -> str:
    if rel == "vault/index.md":
        return "overview"
    if rel.startswith("vault/themes/"):
        return "theme"
    if rel.startswith("vault/subthemes/"):
        return "subtheme"
    if rel.startswith("vault/references/"):
        return "reference"
    return "index"


def _title_for(rel: str) -> str:
    if rel == "vault/index.md":
        return "TellMe Knowledge Base"
    stem = Path(rel).stem.replace("-", " ")
    return " ".join(word.capitalize() for word in stem.split())


def _relative_link(from_rel: str, to_rel: str) -> str:
    if not to_rel:
        return ""
    from_dir = Path(from_rel).parent
    if to_rel.startswith("vault/"):
        return Path(to_rel).relative_to("vault").as_posix() if from_dir.as_posix() == "vault" else (
            "../" + Path(to_rel).relative_to("vault").as_posix()
        )
    if to_rel.startswith("staging/"):
        prefix = "../" if from_dir.as_posix() == "vault" else "../../"
        return prefix + Path(to_rel).as_posix()
    return Path(to_rel).as_posix()


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or "page"
