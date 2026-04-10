from __future__ import annotations

import hashlib
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
    pages = [
        ("vault/index.md", _root_index()),
        ("vault/indexes/concepts.md", _node_index("Concepts", "concept", state.nodes())),
        ("vault/indexes/entities.md", _node_index("Entities", "entity", state.nodes())),
        ("vault/indexes/synthesis.md", _synthesis_index(state.syntheses())),
        ("vault/indexes/unresolved-conflicts.md", _conflict_index(state.conflicts())),
    ]
    written: list[str] = []

    for rel, body in pages:
        path = runtime.data_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_index_page(title=_title_for(rel), body=body, host=host, run_id=run_id), encoding="utf-8")
        state.upsert_page(
            PageRecord(
                path=rel,
                page_type="index",
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


def _root_index() -> str:
    return (
        "## Navigation\n\n"
        "- [Concepts](indexes/concepts.md)\n"
        "- [Entities](indexes/entities.md)\n"
        "- [Synthesis](indexes/synthesis.md)\n"
        "- [Unresolved Conflicts](indexes/unresolved-conflicts.md)\n"
    )


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


def _index_page(title: str, body: str, host: str, run_id: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    return (
        "---\n"
        "page_type: index\n"
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
