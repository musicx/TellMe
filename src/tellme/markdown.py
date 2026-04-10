from __future__ import annotations

import re
from typing import Any


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\r\n")
    return _parse_simple_yaml(raw), body


def extract_wikilinks(text: str) -> set[str]:
    return {match.strip() for match in WIKILINK_RE.findall(text)}


def _parse_simple_yaml(raw: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for line in raw.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip('"').strip("'") for item in value[1:-1].split(",")]
            payload[key] = [item for item in items if item]
        else:
            payload[key] = value.strip('"').strip("'")
    return payload
