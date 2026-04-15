from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ProjectRuntime
from .markdown import parse_frontmatter
from .state import ContentStatus, PageRecord, ProjectState


@dataclass(frozen=True)
class IndexResult:
    index_pages: list[str]


def generate_vault_indexes(
    runtime: ProjectRuntime,
    run_id: str,
    host: str,
    include_reader_facing: bool = True,
) -> IndexResult:
    state = ProjectState.load(runtime.state_dir)
    pages = ([] if not include_reader_facing else _reader_facing_pages(runtime, state)) + [
        ("wiki/indexes/concepts.md", _node_index("Concepts", "concept", state.nodes())),
        ("wiki/indexes/entities.md", _node_index("Entities", "entity", state.nodes())),
        ("wiki/indexes/synthesis.md", _synthesis_index(state.syntheses())),
        ("wiki/indexes/unresolved-conflicts.md", _conflict_index(state.conflicts())),
        ("wiki/indexes/health-review.md", _health_review_index(state.health_findings())),
    ]
    if include_reader_facing:
        _cleanup_stale_reader_facing_pages(runtime=runtime, state=state, desired_paths={rel for rel, _body in pages})
    written: list[str] = []

    for rel, body in pages:
        path = runtime.resolve_path(rel)
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


def _reader_facing_pages(runtime: ProjectRuntime, state: ProjectState) -> list[tuple[str, str]]:
    published_nodes = [
        node
        for node in state.nodes().values()
        if node.get("status") == ContentStatus.PUBLISHED.value
    ]
    themes = _group_themes(published_nodes)
    references = _reference_nodes(published_nodes)
    source_backlog = _source_backlog(runtime, state, published_nodes)

    pages: list[tuple[str, str]] = [("wiki/index.md", _overview_page(themes, references, source_backlog))]
    for theme_name, theme in sorted(themes.items()):
        pages.append((f"wiki/{theme['path']}", _theme_page(theme_name, theme, state)))
        for subtheme_name, subtheme in sorted(theme["subthemes"].items()):
            pages.append((f"wiki/{subtheme['path']}", _subtheme_page(theme_name, subtheme_name, subtheme, state)))
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
        if not published_path.startswith("wiki/references/"):
            continue
        references.append(
            {
                "title": str(node.get("title", node.get("id", "Untitled"))),
                "link": _relative_link("wiki/index.md", published_path),
                "path": published_path,
                "node": node,
            }
        )
    return sorted(references, key=lambda item: item["title"].lower())


def _overview_page(themes: dict[str, dict], references: list[dict], source_backlog: list[dict]) -> str:
    lines = [
        "## 概览",
        "",
        _overview_summary(themes),
        "",
    ]

    if themes:
        lines.extend(["## 推荐阅读路径", ""])
        for theme_name, theme in sorted(themes.items(), key=lambda item: (-len(item[1]["nodes"]), item[0].lower())):
            theme_desc = _first_sentence_from_nodes(theme["nodes"])
            desc_suffix = f" — {theme_desc}" if theme_desc else ""
            lines.append(f"1. [{theme_name}]({theme['path']}){desc_suffix}")
        lines.extend(["", "## 主题地图", ""])
        for theme_name, theme in sorted(themes.items()):
            lines.append(f"- [{theme_name}]({theme['path']})")
            for subtheme_name, subtheme in sorted(theme["subthemes"].items()):
                lines.append(f"  - [{subtheme_name}]({subtheme['path']})")
    else:
        lines.extend(["尚未组织任何读者面向的主题。", ""])

    if references:
        lines.extend(["", "## 核心参考", ""])
        for reference in references:
            ref_summary = str(reference["node"].get("summary", ""))
            desc_suffix = f" — {ref_summary}" if ref_summary else ""
            lines.append(f"- [{reference['title']}]({reference['link']}){desc_suffix}")

    if source_backlog:
        lines.extend(["", "## 待整理来源", ""])
        for item in source_backlog:
            lines.append(f"- [{item['title']}]({item['link']})")

    thin_areas = _thin_areas(themes)
    if thin_areas:
        lines.extend(["", "## 薄弱领域", ""])
        for area in thin_areas:
            lines.append(f"- {area}")

    lines.extend(
        [
            "",
            "## 维护入口",
            "",
            "- [概念索引](indexes/concepts.md)",
            "- [实体索引](indexes/entities.md)",
            "- [综合分析](indexes/synthesis.md)",
            "- [未解决冲突](indexes/unresolved-conflicts.md)",
            "- [健康检查](indexes/health-review.md)",
        ]
    )
    return "\n".join(lines) + "\n"


def _theme_page(theme_name: str, theme: dict, state: ProjectState) -> str:
    lines = [
        "## 概述",
        "",
        _theme_summary(theme_name, theme),
        "",
    ]

    # Theme-level key points aggregated from all nodes
    all_key_points = _collect_key_points(theme["nodes"])
    if all_key_points:
        lines.extend(["## 核心要点", ""])
        for point in all_key_points[:10]:
            lines.append(f"- {point}")
        lines.append("")

    # Subthemes with descriptions
    if theme["subthemes"]:
        lines.extend(["## 子主题", ""])
        for subtheme_name, subtheme in sorted(theme["subthemes"].items()):
            subtheme_desc = _first_sentence_from_nodes(subtheme["nodes"])
            lines.append(f"### [{subtheme_name}](../{subtheme['path']})")
            lines.append("")
            if subtheme_desc:
                lines.append(subtheme_desc)
                lines.append("")
            sub_key_points = _collect_key_points(subtheme["nodes"], limit=3)
            for point in sub_key_points:
                lines.append(f"- {point}")
            if sub_key_points:
                lines.append("")

    # Detailed knowledge per node
    lines.extend(["## 详细内容", ""])
    for node in sorted(theme["nodes"], key=lambda item: str(item.get("title", "")).lower()):
        lines.append(f"### {node['title']}")
        lines.append("")
        content = str(node.get("content", "")).strip()
        if content:
            lines.append(content)
        else:
            lines.append(str(node.get("summary", "尚无详细内容。")))
        lines.append("")

    # Claims as supporting evidence
    claim_lines = _claim_lines(theme["nodes"], state)
    if claim_lines:
        lines.extend(["## 关键论断", ""])
        lines.extend(claim_lines)
        lines.append("")

    # Relationships
    relationship_lines = _relationship_lines(theme["nodes"], state)
    if relationship_lines:
        lines.extend(["## 知识关联", ""])
        lines.extend(relationship_lines)
        lines.append("")

    # References
    reference_nodes = [
        node for node in theme["nodes"] if str(node.get("reader_role", "reference")) == "reference"
    ]
    if reference_nodes:
        lines.extend(["## 参考页面", ""])
        for node in sorted(reference_nodes, key=lambda item: str(item.get("title", "")).lower()):
            lines.append(
                f"- [{node['title']}](../references/{_slug(Path(str(node.get('published_path', node['id']))).stem)}.md)"
            )
        lines.append("")

    # Evidence sources
    theme_sources = sorted({source for node in theme["nodes"] for source in node.get("sources", [])})
    if theme_sources:
        lines.extend(["## 来源", ""])
        for source in theme_sources:
            lines.append(f"- `{source}`")

    return "\n".join(lines).rstrip() + "\n"


def _subtheme_page(theme_name: str, subtheme_name: str, subtheme: dict, state: ProjectState) -> str:
    lines = [
        "## 概述",
        "",
        _subtheme_summary(subtheme_name, subtheme),
        "",
        f"所属主题：[{theme_name}](../themes/{_slug(theme_name)}.md)",
        "",
    ]

    # Key points from this subtheme's nodes
    key_points = _collect_key_points(subtheme["nodes"])
    if key_points:
        lines.extend(["## 核心要点", ""])
        for point in key_points:
            lines.append(f"- {point}")
        lines.append("")

    # Detailed content per node
    lines.extend(["## 详细内容", ""])
    for node in sorted(subtheme["nodes"], key=lambda item: str(item.get("title", "")).lower()):
        lines.append(f"### {node['title']}")
        lines.append("")
        content = str(node.get("content", "")).strip()
        if content:
            lines.append(content)
        else:
            lines.append(str(node.get("summary", "尚无详细内容。")))
        lines.append("")

    # Claims
    claim_lines = _claim_lines(subtheme["nodes"], state)
    if claim_lines:
        lines.extend(["## 关键论断", ""])
        lines.extend(claim_lines)
        lines.append("")

    # Evidence sources
    subtheme_sources = sorted({source for node in subtheme["nodes"] for source in node.get("sources", [])})
    if subtheme_sources:
        lines.extend(["## 来源", ""])
        for source in subtheme_sources:
            lines.append(f"- `{source}`")

    return "\n".join(lines).rstrip() + "\n"


def _reference_page(node: dict, state: ProjectState) -> str:
    lines: list[str] = []

    # Content or summary as main body
    content = str(node.get("content", "")).strip()
    if content:
        lines.extend([content, ""])
    else:
        lines.extend([str(node.get("summary", "尚无详细内容。")), ""])

    # Key points
    key_points = node.get("key_points")
    if isinstance(key_points, list) and key_points:
        lines.extend(["## 核心要点", ""])
        for point in key_points:
            if str(point).strip():
                lines.append(f"- {point}")
        lines.append("")

    # Theme placement
    theme = str(node.get("theme", "")).strip()
    subtheme = str(node.get("subtheme", "")).strip()
    if theme or subtheme:
        lines.extend(["## 所属主题", ""])
        if theme:
            lines.append(f"- 主题：[{theme}](../themes/{_slug(theme)}.md)")
        if subtheme:
            lines.append(f"- 子主题：[{subtheme}](../subthemes/{_slug(theme)}-{_slug(subtheme)}.md)")
        lines.append("")

    # Claims
    claims = [claim for claim in state.claims().values() if claim.get("subject") == node.get("id")]
    if claims:
        lines.extend(["## 关键论断", ""])
        for claim in claims:
            lines.append(f"- {claim['text']}")
        lines.append("")

    # Sources
    sources = node.get("sources", [])
    if sources:
        lines.extend(["## 来源", ""])
        for source in sources:
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
        link = _relative_link(from_rel=f"wiki/indexes/{kind}s.md", to_rel=path) if path else ""
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
        link = _relative_link(from_rel="wiki/indexes/synthesis.md", to_rel=path) if path else ""
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
        link = _relative_link(from_rel="wiki/indexes/unresolved-conflicts.md", to_rel=path) if path else ""
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
        link = _relative_link(from_rel="wiki/indexes/health-review.md", to_rel=path) if path else ""
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
    if rel == "wiki/index.md":
        return "overview"
    if rel.startswith("wiki/themes/"):
        return "theme"
    if rel.startswith("wiki/subthemes/"):
        return "subtheme"
    if rel.startswith("wiki/references/"):
        return "reference"
    return "index"


def _title_for(rel: str) -> str:
    if rel == "wiki/index.md":
        return "TellMe Knowledge Base"
    stem = Path(rel).stem.replace("-", " ")
    return " ".join(word.capitalize() for word in stem.split())


def _relative_link(from_rel: str, to_rel: str) -> str:
    if not to_rel:
        return ""
    from_dir = Path(from_rel).parent
    if to_rel.startswith("wiki/"):
        return Path(to_rel).relative_to("wiki").as_posix() if from_dir.as_posix() == "wiki" else (
            "../" + Path(to_rel).relative_to("wiki").as_posix()
        )
    if to_rel.startswith("staging/"):
        prefix = "../" if from_dir.as_posix() == "wiki" else "../../"
        return prefix + Path(to_rel).as_posix()
    return Path(to_rel).as_posix()


def _slug(value: str) -> str:
    # Preserve non-ASCII letters (e.g. CJK). Only ASCII punctuation and
    # whitespace collapse to `-`. Mirrors tellme.graph._slug contract.
    buf: list[str] = []
    prev_dash = False
    for ch in value.strip():
        if ch in "._-" or (ch.isascii() and ch.isalnum()) or (not ch.isascii() and ch.isalnum()):
            buf.append(ch.lower() if ch.isascii() else ch)
            prev_dash = False
        else:
            if not prev_dash:
                buf.append("-")
                prev_dash = True
    slug = "".join(buf).strip("-")
    return slug or "page"


def _cleanup_stale_reader_facing_pages(
    runtime: ProjectRuntime,
    state: ProjectState,
    desired_paths: set[str],
) -> None:
    managed_prefixes = ("wiki/themes/", "wiki/subthemes/", "wiki/references/")
    for rel_path in list(state.pages()):
        if not rel_path.startswith(managed_prefixes):
            continue
        if rel_path in desired_paths:
            continue
        file_path = runtime.resolve_path(rel_path)
        if file_path.exists():
            file_path.unlink()
        state.delete_page(rel_path)
        state.delete_index(rel_path)


def _overview_summary(themes: dict[str, dict]) -> str:
    if not themes:
        return "尚未组织任何读者面向的主题。"
    # Build a substantive overview from node content
    parts: list[str] = []
    total_nodes = sum(len(theme["nodes"]) for theme in themes.values())
    theme_names = sorted(themes)
    parts.append(f"本知识库围绕 {len(theme_names)} 个主题组织了 {total_nodes} 个知识点。")
    # Add a sentence about each theme based on actual content
    for theme_name in sorted(themes, key=lambda name: -len(themes[name]["nodes"])):
        theme = themes[theme_name]
        desc = _first_sentence_from_nodes(theme["nodes"])
        if desc:
            parts.append(f"**{theme_name}**：{desc}")
        else:
            parts.append(f"**{theme_name}**：包含 {len(theme['nodes'])} 个知识点。")
    return "\n\n".join(parts)


def _thin_areas(themes: dict[str, dict]) -> list[str]:
    areas: list[str] = []
    for theme_name, theme in sorted(themes.items()):
        if len(theme["nodes"]) <= 1:
            areas.append(f"{theme_name} 的已发布内容非常有限。")
        if not theme["subthemes"]:
            areas.append(f"{theme_name} 尚未划分子主题。")
    return areas


def _source_backlog(runtime: ProjectRuntime, state: ProjectState, published_nodes: list[dict]) -> list[dict]:
    represented_sources = {
        source
        for node in published_nodes
        for source in node.get("sources", [])
    }
    backlog: list[dict] = []
    for path, payload in sorted(state.pages().items()):
        if payload.get("page_type") != "source_summary" or payload.get("status") != ContentStatus.PUBLISHED.value:
            continue
        page_sources = [str(source) for source in payload.get("sources", [])]
        if any(source in represented_sources for source in page_sources):
            continue
        file_path = runtime.resolve_path(path)
        backlog.append(
            {
                "title": _page_heading(file_path),
                "link": _relative_link("wiki/index.md", path),
            }
        )
    return backlog


def _page_heading(path: Path) -> str:
    try:
        _frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        return path.stem
    match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else path.stem


def _theme_summary(theme_name: str, theme: dict) -> str:
    """Generate a substantive theme summary from node content."""
    nodes = theme["nodes"]
    if not nodes:
        return f"{theme_name} 尚无已发布的知识内容。"
    # Collect content-based summaries
    summaries: list[str] = []
    for node in sorted(nodes, key=lambda n: str(n.get("title", "")).lower()):
        content = str(node.get("content", "")).strip()
        summary = str(node.get("summary", "")).strip()
        if content:
            # Use first paragraph of content
            first_para = content.split("\n\n")[0].strip()
            summaries.append(first_para)
        elif summary:
            summaries.append(summary)
    if summaries:
        return "\n\n".join(summaries)
    return f"{theme_name} 包含 {len(nodes)} 个知识点，但尚无详细内容。"


def _subtheme_summary(subtheme_name: str, subtheme: dict) -> str:
    """Generate a substantive subtheme summary from node content."""
    nodes = subtheme["nodes"]
    if not nodes:
        return f"{subtheme_name} 尚无已发布的知识内容。"
    summaries: list[str] = []
    for node in sorted(nodes, key=lambda n: str(n.get("title", "")).lower()):
        content = str(node.get("content", "")).strip()
        summary = str(node.get("summary", "")).strip()
        if content:
            first_para = content.split("\n\n")[0].strip()
            summaries.append(first_para)
        elif summary:
            summaries.append(summary)
    if summaries:
        return "\n\n".join(summaries)
    return f"{subtheme_name} 包含 {len(nodes)} 个知识点，但尚无详细内容。"


def _first_sentence_from_nodes(nodes: list[dict]) -> str:
    """Extract the first meaningful sentence from the richest node in the list."""
    for node in sorted(nodes, key=lambda n: -len(str(n.get("content", "")))):
        content = str(node.get("content", "")).strip()
        if content:
            first_line = content.split("\n")[0].strip()
            if len(first_line) > 10:
                return first_line
        summary = str(node.get("summary", "")).strip()
        if summary:
            return summary
    return ""


def _collect_key_points(nodes: list[dict], limit: int = 10) -> list[str]:
    """Collect key_points from nodes, deduplicated and limited."""
    points: list[str] = []
    seen: set[str] = set()
    for node in sorted(nodes, key=lambda n: str(n.get("title", "")).lower()):
        node_points = node.get("key_points")
        if not isinstance(node_points, list):
            continue
        for point in node_points:
            text = str(point).strip()
            if text and text not in seen:
                seen.add(text)
                points.append(text)
                if len(points) >= limit:
                    return points
    return points
