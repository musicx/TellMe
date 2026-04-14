from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectRuntime
from .files import atomic_write_json
from .hosts import KNOWN_HOSTS, HostTask
from .state import ContentStatus, PageRecord, ProjectState


class ReaderRewriteError(RuntimeError):
    """Raised when a reader page rewrite cannot be safely processed."""


@dataclass(frozen=True)
class ReaderRewriteHandoffResult:
    task_json_path: str
    task_markdown_path: str
    result_template_path: str


@dataclass(frozen=True)
class ReaderRewriteConsumeResult:
    result_path: str
    staged_pages: list[str]


def create_reader_rewrite_handoff(runtime: ProjectRuntime, run_id: str, host: str) -> ReaderRewriteHandoffResult:
    state = ProjectState.load(runtime.state_dir)
    reader_pages = sorted(
        {"wiki/index.md"}
        | {
        page_path
        for page_path, payload in state.pages().items()
        if payload.get("status") == ContentStatus.PUBLISHED.value
        and str(payload.get("page_type")) in {"overview", "theme", "subtheme", "reference"}
        and page_path.startswith("wiki/")
        }
    )
    task = HostTask(
        command="reader-rewrite",
        run_id=run_id,
        host=host,
        allowed_read_roots=["raw", "state", "wiki", "staging"],
        allowed_write_roots=["staging", "runs"],
        inputs=reader_pages,
        expected_output=f"staging/reader-rewrite/{run_id}.json",
    )
    task_json = task.write(runtime.runs_dir / run_id / "host-tasks")
    task_markdown = task_json.with_suffix(".md")
    task_markdown.write_text(_task_markdown(task, reader_pages), encoding="utf-8")

    result_template = runtime.runs_dir / run_id / "artifacts" / "reader-rewrite.template.json"
    atomic_write_json(
        result_template,
        {
            "schema_version": 1,
            "candidate_type": "reader_page_rewrites",
            "run_id": run_id,
            "host": host,
            "rewrites": [],
        },
    )
    return ReaderRewriteHandoffResult(
        task_json_path=runtime.relativize_path(task_json),
        task_markdown_path=runtime.relativize_path(task_markdown),
        result_template_path=runtime.relativize_path(result_template),
    )


def consume_reader_rewrite_result(
    runtime: ProjectRuntime,
    result_path: Path,
    consume_run_id: str,
) -> ReaderRewriteConsumeResult:
    resolved = result_path.resolve()
    try:
        resolved.relative_to(runtime.staging_dir.resolve())
    except ValueError as exc:
        raise ReaderRewriteError("reader rewrite result path must be under staging/") from exc
    if not resolved.is_file():
        raise ReaderRewriteError(f"reader rewrite result file not found: {runtime.relativize_path(resolved)}")

    payload = _load_result(resolved)
    state = ProjectState.load(runtime.state_dir)
    staged_pages: list[str] = []

    for rewrite in payload["rewrites"]:
        target_path = str(rewrite["target_path"])
        page_type = str(rewrite["page_type"])
        sources = [str(source) for source in rewrite["sources"]]
        target = runtime.resolve_path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(rewrite["content"]), encoding="utf-8")
        rel = runtime.relativize_path(target)
        state.upsert_page(
            PageRecord(
                path=rel,
                page_type=page_type,
                status=ContentStatus.STAGED,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                sources=sources,
                last_host=str(payload["host"]),
                last_run_id=consume_run_id,
                staged_path=rel,
            )
        )
        staged_pages.append(rel)

    return ReaderRewriteConsumeResult(
        result_path=runtime.relativize_path(resolved),
        staged_pages=staged_pages,
    )


def _load_result(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ReaderRewriteError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ReaderRewriteError("reader rewrite result must be a JSON object")
    if int(payload.get("schema_version", 0)) != 1:
        raise ReaderRewriteError("unsupported reader rewrite schema_version")
    if payload.get("candidate_type") != "reader_page_rewrites":
        raise ReaderRewriteError("candidate_type must be reader_page_rewrites")
    host = str(payload.get("host", ""))
    if host not in KNOWN_HOSTS:
        raise ReaderRewriteError(f"unknown host: {host}")
    rewrites = payload.get("rewrites")
    if not isinstance(rewrites, list):
        raise ReaderRewriteError("rewrites must be a list")
    for rewrite in rewrites:
        if not isinstance(rewrite, dict):
            raise ReaderRewriteError("rewrites must contain objects")
        page_type = str(rewrite.get("page_type", "")).strip()
        if page_type not in {"overview", "theme", "subtheme", "reference"}:
            raise ReaderRewriteError("reader rewrite page_type must be overview, theme, subtheme, or reference")
        target_path = str(rewrite.get("target_path", "")).strip()
        if not target_path.startswith("staging/reader-rewrite/"):
            raise ReaderRewriteError("reader rewrite target_path must be under staging/reader-rewrite/")
        sources = rewrite.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ReaderRewriteError("reader rewrite must include sources")
        if not str(rewrite.get("content", "")).strip():
            raise ReaderRewriteError("reader rewrite must include content")
    return payload


def _task_markdown(task: HostTask, reader_pages: list[str]) -> str:
    pages = "\n".join(f"- `{page}`" for page in reader_pages) or "- No reader-facing pages yet."
    return f"""# TellMe Reader Rewrite Task

Run id: `{task.run_id}`
Host: `{task.host}`

## Goal

改写现有的读者面向页面，使其更易读、更有信息量，同时保留来源可追溯性和页面角色边界。

这是内容深度增强任务，不是表面润色。需要从原始资料中补充解释、论据和细节，使每个页面**自身可读**。

## 语言要求

所有页面内容使用**中文**撰写。

## Allowed Read Roots

- `raw/`
- `state/`
- `wiki/`
- `staging/`

## Allowed Write Roots

- `staging/`
- `runs/`

Do not modify `raw/`.
Do not write directly to `wiki/`.

## Reader-Facing Pages In Scope

{pages}

## Page Role Contracts

Overview 页面（概览）：

- 作为知识库的入口，告诉读者这里有什么、最重要的是什么、如何阅读。
- 每个主题应附带一句话描述其核心内容。
- 引导式阅读路径优先于链接列表。

Theme 页面（主题）：

- 像一本书的章节，不是知识点清单。
- 开头用 2-3 段话概述该主题的核心观点。
- 每个知识点应有完整的详细内容，读者不需要跳转就能理解。
- Claims 和 Relations 作为证据支撑放在内容之后。
- 自适应篇幅：内容丰富时展开，内容薄弱时简洁。

Subtheme 页面（子主题）：

- 解释主题下的一个聚焦分支。
- 每个知识点展开详细内容。
- 与父主题的关系明确说明。

Reference 页面（参考）：

- 简短精确，定义优先。
- 使用节点的 content 作为主体内容。
- 不要膨胀为完整的主题页面。

## Anti-patterns to remove

- 用节点标题拼接成的伪句子（如"本主题围绕 X、Y、Z 组织知识"）
- Claims 或 Relations 列表作为页面主体
- 循环论证（"本主题重要因为它整合了关键想法"）
- 没有实质内容的框架性文字
- 只有 summary 没有展开解释的知识点

## Rewrite Rules

- 从 `raw/` 源文件中提取具体的解释、论据和例子来充实页面。
- 每个知识点的详细内容应自成一体，读者无需跳转即可理解。
- 先解释，后证据。
- 内容自适应：源材料丰富时多段展开，薄弱时简洁陈述。
- 保留来源可追溯性和有效的 markdown 格式。

## Required Result JSON

Use the template at `runs/{task.run_id}/artifacts/reader-rewrite.template.json`.

Each rewrite entry must include:

- `page_type`
- `target_path`
- `sources`
- `content`
"""
