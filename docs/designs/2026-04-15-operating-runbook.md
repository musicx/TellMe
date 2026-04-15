# TellMe 操作 Runbook（2026-04-15）

本文档记录在当前 main（含 Phase 2-A/B/C/D 改动以及 CJK slug 修复之后）环境下，从零到发布的完整操作步骤，以及当前已知坑位。未来若 CLI 行为或路径布局发生变化，应该同步更新本文件。

## 环境前置

- macOS，hostname 返回 `Erics-MacBook-Pro.local`。
- Obsidian vault 在 `/Users/ericliu/Documents/obsidian_vault/llm_wiki/`，其中 `raw/`、`staging/`、`wiki/` 位于 vault 内，`state/`、`runs/` 位于 `~/.tmp/tellme/Users-ericliu-Code-projects-TellMe/`。
- 机器路径绑定由 `config/machines/Erics-MacBook-Pro.local.toml` 描述。
- Python 依赖管理使用 `uv`。

## 一次性准备

```bash
cd /Users/ericliu/Code/projects/TellMe
uv sync
ls config/machines/Erics-MacBook-Pro.local.toml    # 确认机器配置存在
```

安装 `tellme` Claude Code skill（已执行过可跳过）：

```bash
mkdir -p ~/.claude/skills/tellme
ln -sf "$(pwd)/skills/tellme/SKILL.md" ~/.claude/skills/tellme/SKILL.md
```

## 重置 wiki（保留 raw）

```bash
rm -rf /Users/ericliu/Documents/obsidian_vault/llm_wiki/wiki
rm -rf /Users/ericliu/Documents/obsidian_vault/llm_wiki/staging/concepts
rm -rf /Users/ericliu/Documents/obsidian_vault/llm_wiki/staging/entities
rm -rf /Users/ericliu/Documents/obsidian_vault/llm_wiki/staging/graph
rm -rf /Users/ericliu/.tmp/tellme/Users-ericliu-Code-projects-TellMe/state
```

`raw/` 下的原始资料不动。`runs/` 可按需保留（历史审计），如果保留则后续命令仍可以 `--consume-result` 旧 run。

## 完整流水线（5 步）

### 步骤 1：初始化项目

```bash
uv run tellme --project . --machine Erics-MacBook-Pro.local init
```

会重建 `state/`，在 vault 下重建 `staging/` 与 `wiki/` 骨架。

### 步骤 2：注册原始资料

```bash
uv run tellme --project . --machine Erics-MacBook-Pro.local \
  ingest /Users/ericliu/Documents/obsidian_vault/llm_wiki/raw/overview.md
```

`ingest` 接受 vault 内的绝对路径或已映射到 `raw/` 下的相对路径。输出应该是 `tellme ingest: registered raw/overview.md ...`。

### 步骤 3：发起 compile handoff

```bash
uv run tellme --project . --machine Erics-MacBook-Pro.local \
  --host codex compile --handoff
```

CLI 打印两个路径：

- `runs/<run-id>/host-tasks/compile-codex.md` — 任务单（包含 Existing Graph Nodes、Node Quality Rules、语言要求、置信度约定）
- `runs/<run-id>/artifacts/codex-result.template.json` — 结果 JSON 模板

### 步骤 4：LLM 侧做知识抽取

阅读任务单，然后：

1. 写 graph candidate 到 `staging/graph/candidates/<run-id>.json`。
   - 节点 `id = {kind}:{slug(title)}`，kind ∈ {concept, entity}，slug 保留中文。
   - 节点必须有 `summary`（1–2 句中文定义）、`content`（多段中文）、`key_points`（3–7 条）。
   - 对照 Existing Graph Nodes 决定 `update_action_hint`：`create_new` / `enrich_existing` / `uncertain`。
   - claims 和 relations 每条带 `confidence ∈ {extracted, inferred, ambiguous}` 和可选 `confidence_score`。
2. 写 result JSON 到 `runs/<run-id>/artifacts/codex-result.json`，`output_path` 指向刚写的 candidate 文件（相对于 project root）。

### 步骤 5：consume + publish

```bash
# 吸收 candidate，拆成 staging/concepts/*.md 与 staging/entities/*.md
uv run tellme --project . --machine Erics-MacBook-Pro.local \
  --host codex compile --consume-result \
  /Users/ericliu/.tmp/tellme/Users-ericliu-Code-projects-TellMe/runs/<run-id>/artifacts/codex-result.json

# 发布到 wiki/（staged 文件和 PageRecord 在发布成功后自动删除）
uv run tellme --project . --machine Erics-MacBook-Pro.local \
  --host codex publish --all
```

发布后 `wiki/` 应包含：

- `wiki/index.md`
- `wiki/themes/<主题 slug>.md`（保留中文）
- `wiki/subthemes/<主题-子主题 slug>.md`
- `wiki/references/<节点 slug>.md`
- `wiki/indexes/{concepts,entities,synthesis,health-review,unresolved-conflicts}.md`

`staging/` 中保留下来的条目表示"待审核/冲突/uncertain"，语义上有效。

## 日常运维命令

| 场景 | 命令 |
| --- | --- |
| 查看待审 staging | 直接在 Obsidian 打开 `staging/` |
| 基于已发布内容回答问题 | `tellme ... query "问题"`；加 `--stage` 会生成 synthesis candidate |
| 检查漂移/孤儿页/断链 | `tellme ... lint`；加 `--health-handoff` 触发 LLM 健康报告 |
| 吸收 Obsidian 手改 | `tellme ... reconcile` |
| Reader-facing 重写 | `publish --reader-rewrite-handoff` → 做重写 → `publish --consume-reader-rewrite <result>` → `publish --all` |

所有命令同样需要 `--project . --machine Erics-MacBook-Pro.local` 前缀，直到机器自动检测被修复。

## 本次修复要点（2026-04-15）

1. **CJK slug 修复**：`src/tellme/{graph,indexes,health,query}.py` 的 `_slug()` 原先使用 `[^A-Za-z0-9._-]+` 把所有中文压缩为空字符串，导致 `concept:tellme-设计定位` 与 `concept:tellme-本地运行时层` 碰撞到同一文件 `tellme.md`，主题文件也退化为 `tellme.md` / `page.md`。修复后按字符判定 `ch.isalnum()`，非 ASCII 中日韩字符原样保留。
2. **回归验证**：`uv run pytest tests/ -q` → 109 passed。
3. **流水线端到端验证**：4 个 concept/entity 节点各自独立落盘；theme 页面现在有多段中文概述 + 子主题摘要 + key_points + claims + relations，而不是旧模板 "organizes knowledge around X, Y"。

## 已知坑

### `--machine` 自动检测未工作

不带 `--machine` 时 `load_runtime(...)` 会 fallback 到 `~/.obsidian/llm_wiki/` + `~/.tmp/tellme/<slug>/staging`，与 vault 内真实路径不一致，导致 `consume-result` 报 "output file not found"。临时对策：**每条命令都显式传 `--machine Erics-MacBook-Pro.local`**。根因在 `src/tellme/config.py` 的 hostname 归一化或查找键处理，属于独立 follow-up。

### handoff / consume 仅支持 `--host codex`

CLI 对 `--handoff` / `--consume-result` 做了显式 gate，非 codex 宿主会被拒绝。`tellme` skill 的文档需要与此保持一致，或 CLI 需放开到 claude-code / opencode 等。这是一个单独的 skill ↔ CLI 对齐工作。

## 参考

- 设计基线：`docs/designs/2026-04-10-knowledge-graph-mvp-redesign.md`
- Reader 页面模型：`docs/designs/2026-04-10-reader-facing-knowledge-organization-redesign.md`
- Skill 契约：`skills/tellme/SKILL.md`
- 机器路径：`config/machines/Erics-MacBook-Pro.local.toml`
