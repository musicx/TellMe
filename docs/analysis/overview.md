# TellMe 参考实现总览

本目录分析了 `E:\Code\git\genai-related\llm-wiki\` 下的 5 个参考实现。TellMe 的目标不是复制其中任意一个，而是组合它们的优点，同时修正它们对多宿主、跨平台和内容治理不足的问题。

## 参考项目列表

- `llm-knowledge-base`
- `llm-wiki-plugin`
- `obsidian-llm-wiki-local`
- `obsidian-wiki`
- `second-brain`

## 快速结论

### 1. TellMe 不应做成纯技能包

`obsidian-wiki` 和 `second-brain` 在多宿主兼容上做得很好，但它们把大量一致性责任交给宿主和提示词，缺少真正的运行时状态层。对于 TellMe 来说，这会让多模型、多宿主协作时的漂移问题变得难以管理。

### 2. TellMe 需要真正的本地运行时

`obsidian-llm-wiki-local` 提供了更接近产品形态的答案：CLI、状态库、配置、watcher、草稿审核和测试。这一类实现证明了 TellMe 应该拥有自己的运行时，而不是只提供提示词和技能目录。

### 3. TellMe 仍然要保留宿主入口层

`llm-wiki-plugin`、`obsidian-wiki`、`second-brain` 的共同经验是：用户确实希望从熟悉的 agent 宿主进入系统，而不是被迫学习一套完全独立的交互方式。TellMe 需要把 `Claude Code`、`Codex`、`OpenCode` 视为“入口协议”，而不是“附带支持”。

### 4. TellMe 需要比参考实现更强的 reconcile 机制

现有参考实现普遍强调 ingest、query、lint，但很少把“宿主直接改了 Obsidian 内容之后怎么办”设计成一等公民。TellMe 的差异化价值之一，就是把 `reconcile` 设计成正式命令和正式状态机。

## 对比矩阵

| 项目 | 技术形态 | 宿主兼容 | 状态管理 | 发布策略 | TellMe 可复用点 | 主要不足 |
| --- | --- | --- | --- | --- | --- | --- |
| `llm-knowledge-base` | Claude Code 技能 + Python 搜索脚本 | 低 | 中 | 中 | compile / reflect / ask 生命周期 | 偏 Claude，配置较单一 |
| `llm-wiki-plugin` | Claude 插件 | 低 | 低 | 中 | 指令路由、qmd/Marp 集成思路 | 强依赖 Claude 插件和固定 vault 约定 |
| `obsidian-llm-wiki-local` | Python CLI | 低到中 | 高 | 高 | CLI、配置、状态库、草稿审批 | 假设本地 Ollama，宿主适配薄 |
| `obsidian-wiki` | 纯技能框架 | 高 | 低 | 低 | 多宿主 bootstrap、技能分发 | 缺少真正运行时与统一状态 |
| `second-brain` | agent-skills 分发 | 高 | 低到中 | 中 | onboarding、agent-agnostic 包装 | 以技能安装为中心，控制面偏弱 |

## TellMe 应采纳的能力

- 从 `obsidian-llm-wiki-local` 采纳：Python 核心、TOML 配置、状态数据库、草稿工作流、健康检查思路。
- 从 `obsidian-wiki` 采纳：多宿主 bootstrap、统一技能语义、配置文件分发策略。
- 从 `second-brain` 采纳：以用户工作流为中心的 onboarding 设计，以及 agent-agnostic 的项目叙述方式。
- 从 `llm-knowledge-base` 采纳：`ingest / compile / reflect / ask / lint / merge` 这种完整知识生命周期视角。
- 从 `llm-wiki-plugin` 采纳：单一入口命令路由和可选外部工具集成思路。

## TellMe 应避免的设计

- 避免把路径硬编码到单一平台或单一 vault 位置。
- 避免把核心状态藏在宿主目录或用户主目录中，导致项目不可移植。
- 避免只靠 prompt 约束内容一致性，而不建立显式状态与 reconcile。
- 避免把 `vault/` 与内部状态混在一起，导致 Obsidian 插件、人工修改和系统元数据相互污染。

## 建议阅读顺序

1. `obsidian-llm-wiki-local.md`
2. `obsidian-wiki.md`
3. `second-brain.md`
4. `llm-knowledge-base.md`
5. `llm-wiki-plugin.md`
