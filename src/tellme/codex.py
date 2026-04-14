from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .config import ProjectRuntime
from .files import atomic_write_json
from .graph import GraphCandidateError, is_graph_candidate_path, stage_graph_candidate
from .hosts import HostResult, HostTask, HostValidationError
from .markdown import parse_frontmatter
from .state import ContentStatus, PageRecord, ProjectState, SourceRecord


class CodexResultError(RuntimeError):
    """Raised when Codex output cannot be safely consumed by TellMe."""


class CodexHandoffError(RuntimeError):
    """Raised when Codex handoff context cannot be safely prepared."""


@dataclass(frozen=True)
class CodexHandoffResult:
    task_json_path: str
    task_markdown_path: str
    result_template_path: str
    source_references: list[str]


@dataclass(frozen=True)
class CodexConsumeResult:
    staged_page: str
    source_references: list[str]
    staged_pages: list[str]


def create_codex_handoff(
    runtime: ProjectRuntime,
    run_id: str,
    health_finding_id: str | None = None,
) -> CodexHandoffResult:
    state = ProjectState.load(runtime.state_dir)
    health_finding = None
    if health_finding_id is not None:
        health_finding = state.health_findings().get(health_finding_id)
        if not health_finding:
            raise CodexHandoffError(f"unknown health finding: {health_finding_id}")
        if health_finding.get("status") != ContentStatus.STAGED.value:
            raise CodexHandoffError(f"health finding is not staged: {health_finding_id}")
        source_references = sorted(str(source) for source in health_finding.get("sources", []))
    else:
        source_references = sorted(
            SourceRecord.from_dict(payload).path for payload in state.sources().values()
        )
    graph_nodes = state.nodes()
    graph_relations = state.relations()
    task = HostTask(
        command="compile",
        run_id=run_id,
        host="codex",
        allowed_read_roots=["raw", "state", "wiki", "staging"],
        allowed_write_roots=["staging", "runs"],
        inputs=source_references,
        expected_output=f"runs/{run_id}/artifacts/codex-result.json",
    )
    task_json = task.write(runtime.runs_dir / run_id / "host-tasks")
    task_markdown = task_json.with_suffix(".md")
    task_markdown.write_text(
        _task_markdown(
            task,
            source_references,
            graph_nodes,
            graph_relations,
            health_finding,
        ),
        encoding="utf-8",
    )

    result_template = runtime.runs_dir / run_id / "artifacts" / "codex-result.template.json"
    atomic_write_json(
        result_template,
        {
            "schema_version": 1,
            "status": "succeeded",
            "host": "codex",
            "run_id": run_id,
            "output_path": f"staging/graph/candidates/{run_id}.json",
            "source_references": source_references,
            "graph_candidate": {
                "schema_version": 1,
                "candidate_type": "knowledge_graph_update",
                "source_references": source_references,
                "nodes": [
                    {
                        "_comment": "example node - delete and replace with real nodes. id must follow {kind}:{slug(title)} rule.",
                        "id": "concept:example",
                        "kind": "concept",
                        "title": "Example Concept",
                        "summary": "1-2 sentence Chinese definition for index display.",
                        "content": "Multi-paragraph Chinese explanation.\n\nSecond paragraph with details.",
                        "key_points": [
                            "Key point 1 as a complete Chinese sentence.",
                            "Key point 2 as a complete Chinese sentence.",
                        ],
                        "sources": ["raw/example.md"],
                        "update_action_hint": "create_new",
                    }
                ],
                "claims": [
                    {
                        "_comment": "example claim - confidence is optional but recommended",
                        "id": "claim:example-assertion",
                        "subject": "concept:example",
                        "text": "核心论断的中文陈述。",
                        "sources": ["raw/example.md"],
                        "confidence": "extracted",
                        "confidence_score": 0.9,
                    }
                ],
                "relations": [
                    {
                        "_comment": "example relation - confidence labels: extracted | inferred | ambiguous",
                        "source": "concept:example",
                        "target": "concept:other",
                        "type": "depends_on",
                        "sources": ["raw/example.md"],
                        "confidence": "inferred",
                        "confidence_score": 0.6,
                    }
                ],
                "conflicts": [],
            },
            "confidence": "review-required",
            "errors": [],
        },
    )

    return CodexHandoffResult(
        task_json_path=runtime.relativize_path(task_json),
        task_markdown_path=runtime.relativize_path(task_markdown),
        result_template_path=runtime.relativize_path(result_template),
        source_references=source_references,
    )


def consume_codex_result(
    runtime: ProjectRuntime,
    result_path: Path,
    consume_run_id: str,
) -> CodexConsumeResult:
    try:
        result = HostResult.load(result_path)
    except (HostValidationError, KeyError, json.JSONDecodeError, OSError) as exc:
        raise CodexResultError(str(exc)) from exc

    if result.host != "codex":
        raise CodexResultError(f"expected codex result, got {result.host}")
    if result.status != "succeeded":
        raise CodexResultError(f"codex result status is not succeeded: {result.status}")

    output_path = runtime.resolve_path(result.output_path)
    try:
        output_path.relative_to(runtime.staging_dir.resolve())
    except ValueError as exc:
        raise CodexResultError("codex output_path must be under staging/") from exc
    if not output_path.is_file():
        raise CodexResultError(f"codex output file not found: {result.output_path}")

    if is_graph_candidate_path(output_path):
        try:
            graph_result = stage_graph_candidate(
                runtime=runtime,
                candidate_path=output_path,
                host="codex",
                run_id=consume_run_id,
                expected_source_references=result.source_references,
            )
        except GraphCandidateError as exc:
            raise CodexResultError(str(exc)) from exc
        staged_page = graph_result.staged_pages[0] if graph_result.staged_pages else runtime.relativize_path(output_path)
        return CodexConsumeResult(
            staged_page=staged_page,
            staged_pages=graph_result.staged_pages,
            source_references=result.source_references,
        )

    rel = runtime.relativize_path(output_path)
    frontmatter, _body = parse_frontmatter(output_path.read_text(encoding="utf-8"))
    page_type = str(frontmatter.get("page_type", "codex_candidate")) if frontmatter else "codex_candidate"
    state = ProjectState.load(runtime.state_dir)
    state.upsert_page(
        PageRecord(
            path=rel,
            page_type=page_type,
            status=ContentStatus.STAGED,
            sha256=hashlib.sha256(output_path.read_bytes()).hexdigest(),
            sources=result.source_references,
            last_host="codex",
            last_run_id=consume_run_id,
            staged_path=rel,
        )
    )
    return CodexConsumeResult(staged_page=rel, staged_pages=[rel], source_references=result.source_references)


def _task_markdown(
    task: HostTask,
    source_references: list[str],
    graph_nodes: dict[str, dict],
    graph_relations: dict[str, dict],
    health_finding: dict | None,
) -> str:
    sources = "\n".join(f"- `{source}`" for source in source_references) or "- No registered sources."
    filtered_nodes, filter_note = _select_relevant_existing_nodes(
        graph_nodes, graph_relations, source_references
    )
    existing_nodes = _existing_nodes_markdown(filtered_nodes)
    health_finding_section = _health_finding_markdown(health_finding)
    return f"""# TellMe Codex Compile Task

Run id: `{task.run_id}`
Command: `{task.command}`
Host: `codex`

## Goal

从注册的 TellMe 源文件中提取结构化知识图谱更新候选。对每个知识点，提取**详细解释、关键论点和证据链**，而不仅仅是标题和一句话摘要。将候选 JSON 写入 `staging/graph/candidates/`，将结果 JSON 写入 `{task.expected_output}`。

## 核心工作模式

### 知识过滤（最重要）

**不要**无脑提取源文件中的所有概念。你的核心任务是**知识过滤**：

1. **对比已有图谱**：先仔细阅读下方的 Existing Graph Nodes，理解当前知识库已覆盖的范围。
2. **补充已有节点**：如果源文件中的内容可以丰富已有节点（更多细节、新论据、新视角），设置 `update_action_hint: "enrich_existing"` 并在 `content` 中合并新旧内容。**必须复用已有节点的 `id`**，不要改名重建。
3. **发现矛盾**：如果源文件与已有知识点有冲突，生成 `conflicts` 条目并附上双方的证据。
4. **新建节点**：只有当源文件包含**已有图谱中不存在的独立知识点**时，才 `update_action_hint: "create_new"`。
5. **不确定**：如果拿不准该补充哪个已有节点，或该节点是否应该独立，使用 `update_action_hint: "uncertain"`。不确定的节点会被自动进入人工 review，不会直接发布。**宁可标 uncertain 也不要猜**。

### 节点 ID 规约

新建节点时 `id` 必须按以下规则生成：

- 格式 `{{kind}}:{{slug}}`，kind 是 `concept` 或 `entity`。
- slug 由 `title` 派生：小写，空格和 ASCII 标点替换为单个 `-`，连续 `-` 合并，首尾 `-` 去掉。中文字符**保留**。
- 示例：`title = "TellMe 控制面"` → `id = "concept:tellme-控制面"`；`title = "Codex Graph Candidate"` → `id = "concept:codex-graph-candidate"`。
- 同一个概念务必产生同一个 id（这样下次抽取能自动对齐到已有节点）。

补充已有节点时**直接复用**已有 id，不要用新规则重新生成（即使格式看起来不一致）。

### 置信度标记（borrowed from graphify）

每条 `claim` 和 `relation` 建议附带置信度标签，便于后续 lint 和发布时过滤：

- `confidence: "extracted"` — 源文中有明确的文字或符号直接支持这个断言/关系（引用、"见第 3.2 节"、调用/导入等）。
- `confidence: "inferred"` — 基于合理推断得出（共享数据结构、隐含依赖、语义相似）。
- `confidence: "ambiguous"` — 不确定，需要 review。**不要省略——标 ambiguous 比丢弃更有价值**。
- 可选 `confidence_score`：0.0–1.0 的数值估计，便于排序。

节点之间的 `theme`/`subtheme` 字段**不需要**置信度标记。

### 内容深度要求

这不是元数据提取任务。每个节点必须有足够的内容，让读者**只看这个节点就能理解它说了什么**。

- `summary`：1-2 句话的简短定义，用于索引和列表展示。
- `content`（必须提供）：多段落的详细解释，包括：
  - 这个概念/实体是什么
  - 为什么它重要
  - 它的核心论点或机制
  - 关键的细节和例子
  - 与其他知识点的联系
- `key_points`（必须提供）：3-7 个结构化的关键要点，每个要点是一句完整的陈述。

### 语言要求

所有节点的 `summary`、`content`、`key_points` 使用**中文**撰写。`id` 和结构性字段保持英文。claim 的 `text` 使用中文。

## Allowed Read Roots

- `raw/`
- `state/`
- `wiki/`
- `staging/`

## Allowed Write Roots

- `staging/`
- `runs/`

Do not modify `raw/`.
Do not publish directly to `wiki/`.

## Input Sources

{sources}

{health_finding_section}

## Existing Graph Nodes

{filter_note}{existing_nodes}

## Required Result JSON

Use the template at `runs/{task.run_id}/artifacts/codex-result.template.json`.
The final result JSON must include `schema_version`, `status`, `host`, `run_id`, `output_path`, and `source_references`.

The `output_path` file must be a graph candidate JSON with:

- `candidate_type: "knowledge_graph_update"`
- `source_references`: raw evidence paths used by this candidate
- `nodes`: concept/entity nodes with `id`, `kind`, `title`, `summary`, `content`, `key_points`, `sources`, and optional `update_action_hint`
- `claims`: atomic sourced statements with `id`, `subject`, `text`, `sources`, optional `confidence` and `confidence_score`
- `relations`: sourced edges with `source`, `target`, `type`, `sources`, optional `confidence` and `confidence_score`
- `conflicts`: apparent contradictions or tensions with source-backed explanation candidates

## Node Quality Rules

For each node:

- `summary`（必填）：1-2 句中文定义，用于索引。不要把详细内容塞进 summary。
- `content`（强烈建议）：多段落的中文详细解释。这是知识点的核心内容载体。应包含：
  - 概念的定义和上下文
  - 核心论点、机制或原理的解释
  - 关键细节和具体例子
  - 与其他知识领域的联系
  - 篇幅自适应：简单概念 2-3 段，复杂话题 4-6 段
- `key_points`（强烈建议）：3-7 个中文关键要点，每个是一句完整的陈述句。
- If the node clearly belongs in a chapter-like topic, include optional `theme` and `subtheme`.
- Choose optional `reader_role` deliberately:
  - `reference` for stable pages that should stand alone in the published wiki
  - `embedded` for supporting ideas that should mainly strengthen theme or subtheme pages
- Include optional `promotion_recommendation` when you can justify publication intent:
  - `reference` when the node is worth a standalone reader-facing page
  - `embedded` when it mainly belongs inside a larger theme page
  - `theme_candidate` when the idea points toward a broader chapter-like organization need
  - `hold` when the evidence is real but promotion should wait for more corpus support
- Include optional `promotion_reason` to explain the recommendation in one sentence.
- Include optional `standalone_value` and `theme_fit` using `low`, `medium`, or `high`.
- Prefer fewer, stronger nodes over many thin, overlapping nodes.
"""


_EXISTING_NODE_BUDGET = 80


def _select_relevant_existing_nodes(
    graph_nodes: dict[str, dict],
    graph_relations: dict[str, dict],
    source_references: list[str],
    max_count: int = _EXISTING_NODE_BUDGET,
) -> tuple[dict[str, dict], str]:
    """Filter existing nodes down to a manageable subset for the compile handoff.

    Strategy:
    - If the full graph is small enough, send everything.
    - Otherwise prioritize (a) nodes whose sources overlap with this run's
      source_references, then (b) "god nodes" by relation degree, up to a cap.
    """

    if not graph_nodes:
        return {}, ""
    if len(graph_nodes) <= max_count:
        return graph_nodes, ""

    source_set = {str(s) for s in source_references}

    # (a) Nodes sharing a source with this handoff.
    overlap_ids: list[str] = []
    for node_id, node in graph_nodes.items():
        node_sources = {str(s) for s in node.get("sources") or []}
        if node_sources & source_set:
            overlap_ids.append(node_id)

    # (b) Degree from state relations.
    degree: dict[str, int] = {}
    for relation in graph_relations.values():
        for key in ("source", "target"):
            rid = str(relation.get(key, ""))
            if rid in graph_nodes:
                degree[rid] = degree.get(rid, 0) + 1
    god_ids = sorted(degree, key=lambda rid: (-degree[rid], rid))

    selected: dict[str, dict] = {}
    for node_id in overlap_ids:
        if len(selected) >= max_count:
            break
        selected[node_id] = graph_nodes[node_id]
    for node_id in god_ids:
        if len(selected) >= max_count:
            break
        if node_id not in selected:
            selected[node_id] = graph_nodes[node_id]

    filter_note = (
        f"_Showing {len(selected)} of {len(graph_nodes)} existing nodes "
        f"(overlap with this run's sources + top-degree nodes). "
        f"If you need to check for overlap with a node not listed here, "
        f"consult `state/` directly._\n\n"
    )
    return selected, filter_note


def _existing_nodes_markdown(graph_nodes: dict[str, dict]) -> str:
    if not graph_nodes:
        return "- No existing graph nodes."
    lines: list[str] = []
    for node_id, node in sorted(graph_nodes.items()):
        title = str(node.get("title", node_id))
        kind = str(node.get("kind", "node"))
        status = str(node.get("status", "unknown"))
        published_path = node.get("published_path")
        path_suffix = f" -> `{published_path}`" if published_path else ""
        lines.append(f"- `{node_id}` ({kind}, {status}): {title}{path_suffix}")
    return "\n".join(lines)


def _health_finding_markdown(health_finding: dict | None) -> str:
    if not health_finding:
        return ""
    affected_ids = "\n".join(
        f"- `{affected_id}`" for affected_id in health_finding.get("affected_ids", [])
    ) or "- No affected ids."
    staged_path = str(health_finding.get("staged_path", ""))
    staged_path_line = f"- review page: `{staged_path}`\n" if staged_path else ""
    return (
        "## Health Finding Focus\n\n"
        "This handoff is focused on an existing staged health finding. Use it to guide the next graph update.\n\n"
        f"- finding id: `{health_finding['id']}`\n"
        f"- finding type: `{health_finding['finding_type']}`\n"
        f"- summary: {health_finding['summary']}\n"
        f"{staged_path_line}"
        f"- suggested_next_action: {health_finding.get('suggested_next_action', 'manual_review')}\n\n"
        "### Recommendation\n\n"
        f"{health_finding['recommendation']}\n\n"
        "### Affected IDs\n\n"
        f"{affected_ids}\n"
    )
