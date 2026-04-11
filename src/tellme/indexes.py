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
        pages.append((f"vault/{theme['path']}", _theme_page(theme_name, theme, state)))
        for subtheme_name, subtheme in sorted(theme["subthemes"].items()):
            pages.append((f"vault/{subtheme['path']}", _subtheme_page(theme_name, subtheme_name, subtheme, state)))
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
    lines = [
        "## Summary",
        "",
        _overview_summary(themes),
        "",
        "## Recommended Reading Path",
        "",
    ]
    if not themes:
        lines.append("No reader-facing themes yet.")
    else:
        for theme_name, theme in sorted(themes.items(), key=lambda item: (-len(item[1]["nodes"]), item[0].lower())):
            lines.append(f"1. [{theme_name}]({theme['path']})")
    lines.extend(["", "## Theme Map", ""])
    if not themes:
        lines.append("No reader-facing themes yet.")
    else:
        for theme_name, theme in sorted(themes.items()):
            lines.append(f"- [{theme_name}]({theme['path']})")
            if theme["subthemes"]:
                for subtheme_name, subtheme in sorted(theme["subthemes"].items()):
                    lines.append(f"- [{subtheme_name}]({subtheme['path']})")
    lines.extend(["", "## Key References", ""])
    if not references:
        lines.append("No promoted reference pages yet.")
    else:
        for reference in references:
            lines.append(f"- [{reference['title']}]({reference['link']})")
    lines.extend(["", "## Thin Areas", ""])
    thin_areas = _thin_areas(themes)
    if not thin_areas:
        lines.append("No obvious thin areas yet.")
    else:
        for area in thin_areas:
            lines.append(f"- {area}")
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


def _theme_page(theme_name: str, theme: dict, state: ProjectState) -> str:
    lines = [
        "## Summary",
        "",
        _theme_summary(theme_name, theme),
        "",
        "## Why This Theme Matters",
        "",
        _theme_importance(theme_name, theme),
        "",
        "## Core Question",
        "",
        f"What does {theme_name} mean in this knowledge base, and how do its subtopics fit together?",
        "",
        "## Subthemes",
        "",
    ]
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
    lines.extend(["", "## Key Claims", ""])
    claim_lines = _claim_lines(theme["nodes"], state)
    if not claim_lines:
        lines.append("No key claims yet.")
    else:
        lines.extend(claim_lines)
    lines.extend(["", "## Relationships", ""])
    relationship_lines = _relationship_lines(theme["nodes"], state)
    if not relationship_lines:
        lines.append("No explicit relationships yet.")
    else:
        lines.extend(relationship_lines)
    lines.extend(["", "## Coverage", ""])
    for node in sorted(theme["nodes"], key=lambda item: str(item.get("title", "")).lower()):
        lines.append(f"### {node['title']}")
        lines.append("")
        lines.append(str(node.get("summary", "No summary available.")))
        lines.append("")
    lines.extend(["## Evidence", ""])
    theme_sources = sorted({source for node in theme["nodes"] for source in node.get("sources", [])})
    if not theme_sources:
        lines.append("No evidence sources yet.")
    else:
        for source in theme_sources:
            lines.append(f"- `{source}`")
    return "\n".join(lines).rstrip() + "\n"


def _subtheme_page(theme_name: str, subtheme_name: str, subtheme: dict, state: ProjectState) -> str:
    lines = [
        "## Summary",
        "",
        _subtheme_summary(subtheme_name, subtheme),
        "",
        "## How This Fits",
        "",
        f"{subtheme_name} is one part of {theme_name} and should be read as a focused slice of that larger theme.",
        "",
        "## Parent Theme",
        "",
        f"- [{theme_name}](../themes/{_slug(theme_name)}.md)",
        "",
        "## Key Claims",
        "",
    ]
    claim_lines = _claim_lines(subtheme["nodes"], state)
    if not claim_lines:
        lines.append("No key claims yet.")
    else:
        lines.extend(claim_lines)
    lines.extend([
        "",
        "## Covered Knowledge",
        "",
    ])
    for node in sorted(subtheme["nodes"], key=lambda item: str(item.get("title", "")).lower()):
        lines.append(f"### {node['title']}")
        lines.append("")
        lines.append(str(node.get("summary", "No summary available.")))
        lines.append("")
    lines.extend(["## Evidence", ""])
    subtheme_sources = sorted({source for node in subtheme["nodes"] for source in node.get("sources", [])})
    if not subtheme_sources:
        lines.append("No evidence sources yet.")
    else:
        for source in subtheme_sources:
            lines.append(f"- `{source}`")
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


def _claim_lines(nodes: list[dict], state: ProjectState) -> list[str]:
    node_ids = {str(node.get("id", "")) for node in nodes}
    claims = [
        claim for claim in state.claims().values() if str(claim.get("subject", "")) in node_ids
    ]
    return [f"- {claim['text']}" for claim in claims]


def _relationship_lines(nodes: list[dict], state: ProjectState) -> list[str]:
    node_ids = {str(node.get("id", "")) for node in nodes}
    titles = {
        str(node.get("id", "")): str(node.get("title", node.get("id", "Untitled")))
        for node in state.nodes().values()
    }
    relations = [
        relation for relation in state.relations().values() if str(relation.get("source", "")) in node_ids
    ]
    lines: list[str] = []
    for relation in relations:
        target_id = str(relation.get("target", ""))
        target_title = titles.get(target_id, target_id)
        lines.append(f"- {titles.get(str(relation['source']), str(relation['source']))} {relation['type']} {target_title}")
    return lines


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


def _overview_summary(themes: dict[str, dict]) -> str:
    if not themes:
        return "No reader-facing themes have been organized yet."
    names = sorted(themes)
    if len(names) == 1:
        return f"This knowledge base is currently organized around the theme {names[0]}."
    preview = ", ".join(names[:3])
    return f"This knowledge base is currently organized around the themes {preview}."


def _thin_areas(themes: dict[str, dict]) -> list[str]:
    areas: list[str] = []
    for theme_name, theme in sorted(themes.items()):
        if len(theme["nodes"]) <= 1:
            areas.append(f"{theme_name} has very little published coverage.")
        if not theme["subthemes"]:
            areas.append(f"{theme_name} has no subthemes yet.")
    return areas


def _theme_summary(theme_name: str, theme: dict) -> str:
    node_titles = [str(node.get("title", "Untitled")) for node in theme["nodes"]]
    if not node_titles:
        return f"{theme_name} does not have any published knowledge yet."
    preview = ", ".join(node_titles[:3])
    return f"{theme_name} currently organizes knowledge around {preview}."


def _theme_importance(theme_name: str, theme: dict) -> str:
    node_titles = [str(node.get("title", "Untitled")) for node in theme["nodes"]]
    preview = ", ".join(node_titles[:2]) if node_titles else theme_name
    return f"This theme matters because it groups together the key ideas and references around {preview}."


def _subtheme_summary(subtheme_name: str, subtheme: dict) -> str:
    node_titles = [str(node.get("title", "Untitled")) for node in subtheme["nodes"]]
    if not node_titles:
        return f"{subtheme_name} does not have any published knowledge yet."
    preview = ", ".join(node_titles[:3])
    return f"{subtheme_name} focuses on {preview}."
