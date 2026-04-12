# TellMe Agent Contract

本文件定义 Codex 及其他 `AGENTS.md` 感知宿主在 TellMe 项目中的工作约束。

## 项目定位

TellMe 是一个混合式 LLM-wiki 编排器：

- `TellMe` 负责项目状态、配置、生命周期、发布策略与 reconcile。
- `Obsidian` 负责展示 `wiki/` 中的已发布知识点 wiki graph。
- `Claude Code`、`Codex`、`OpenCode` 作为宿主接入同一项目。

## 真实控制面

宿主必须把以下目录视为系统真相来源，但这些目录不应位于源码 repo 根目录。它们应位于 `$OBSIDIAN_VAULT_PATH`、机器配置指定目录或 fallback 数据根目录下：

- `config/`
- `state/`
- `runs/`
- `raw/`
- `staging/`

`wiki/` 不是完整系统状态，只是面向 Obsidian 的发布目录。

## 知识图谱目标

TellMe 的最终 wiki 不应是一组 raw document mirror。宿主加工 raw 时，应抽取核心概念、实体、claim 和 relation，对照已有 wiki graph，优先补充已有知识点；只有不存在对应节点时才新建节点。发现矛盾时，不应直接覆盖，应生成 conflict 或 explanation candidate 并进入 `staging/`。

Karpathy LLM-wiki 对齐要求 TellMe 还应支持探索结果累积：query/output 不应只停留在 terminal 或 `runs/`，有价值的输出应能作为 synthesis/output candidate 回流到 `staging/`，经审核发布到 `wiki/`。Obsidian 应逐步成为 raw、compiled graph、review queue、synthesis/output 和健康检查结果的统一 IDE surface。

## 核心规则

1. 不得直接改写 `raw/` 中的原始资料。
2. 任何自动生成或自动更新的页面都必须保留最小 frontmatter。
3. 任何正式操作都应写入 `runs/` 记录。
4. 允许人工直接修改 `wiki/`，但后续必须通过 `tellme reconcile` 吸收差异。
5. 遇到人工修改与自动修改冲突时，默认保留人工版本，并将自动候选退回 `staging/`。
6. 宿主不得把 `Obsidian` 视为主数据库；主数据库是 TellMe 项目目录本身。
7. 若需要新增宿主适配规则，优先更新 `config/hosts/` 和本文件，而不是把约束散落到多个笔记中。

## 正式命令语义

- `tellme init`: 初始化项目、配置、目录和宿主适配文件
- `tellme ingest`: 注册并分析原始资料
- `tellme compile`: 从 `raw/` 生成或更新知识点、claim、relation、conflict 等 graph 候选内容
- `tellme query`: 基于已发布内容回答问题；`--stage` 可生成 source-backed synthesis candidate
- `tellme lint`: 检查断链、孤儿页、frontmatter、索引漂移、来源缺失；`--health-handoff` 可生成 LLM health/reflection 任务，`--consume-health-result` 可登记 staged health finding 并生成 review 页面，`--resolve-health-finding` 可关闭已处理的 finding
- `tellme reconcile`: 扫描宿主直接修改并修正状态与索引
- `tellme publish`: 将已审核的 staged graph node、synthesis、output 发布到 `wiki/`，并刷新 Obsidian index pages

## 文档入口

- 设计文档：`docs/designs/2026-04-10-knowledge-graph-mvp-redesign.md`
- Karpathy 对齐设计：`docs/designs/2026-04-10-karpathy-llm-wiki-design-update.md`
- 参考实现分析：`docs/analysis/reference-capability-summary-2026-04-10.md`
- 项目配置：`config/project.toml`

## 当前阶段

当前仓库处于本地 orchestrator V1 阶段。七个正式命令已有基础行为，Codex handoff/consume 已接入第一版 graph candidate protocol，handoff 会暴露已有 graph nodes，consume 会标记 `create_new` 或 `enrich_existing`，并将 concept/entity 节点、claims、relations、conflicts 写入 state。Karpathy feedback loop 的第一版也已具备：`query --stage` 生成 synthesis candidate，`publish --all` 发布 graph/synthesis/output 并刷新 Obsidian indexes，`lint --health-handoff` 生成 LLM health/reflection 任务，`lint --consume-health-result` 会把 finding 写入 `state.health_findings`、生成 `staging/health/*.md` review 页面，并在 `wiki/indexes/health-review.md` 暴露 review queue，`compile --handoff --health-finding <id>` 可从单条 finding 发起 focused graph work，`lint --resolve-health-finding <id>` 可在处理后关闭该 finding。reader-facing 知识组织重设计的第一实现切片也已开始落地：TellMe 会生成 `wiki/index.md`、`wiki/themes/`、`wiki/subthemes/` 与 `wiki/references/` 作为阅读层，而 `wiki/indexes/` 继续承担维护视角。完整迁移历史 concept/entity 内容、主题文案强化和更强的组织决策仍在后续范围。若宿主继续实现代码，应先遵循 `docs/designs/2026-04-10-knowledge-graph-mvp-redesign.md` 与 `docs/designs/2026-04-10-reader-facing-knowledge-organization-redesign.md` 中的边界，不要绕开既定目录分层与配置模型。

## Codex 协作约束

Codex 参与内容生成时应优先使用 TellMe 的文件型 handoff：

1. 由用户或宿主运行 `tellme --host codex compile --handoff`。
2. Codex 读取 `runs/<run-id>/host-tasks/compile-codex.md`。
3. Codex 只写入 `staging/` 和 `runs/`，不得直接修改 `raw/` 或发布到 `wiki/`。
4. Codex 写完 graph candidate JSON 和 result JSON 后，由 `tellme --host codex compile --consume-result <result.json>` 登记状态。
5. 审核 `staging/` 后，由 `tellme --host codex publish --all` 发布 graph node 到 `wiki/`。
