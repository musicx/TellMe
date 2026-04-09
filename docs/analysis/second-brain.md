# `second-brain` 技术分析

## 项目定位

`second-brain` 是一个通过 `npx skills add` 分发的 agent-skills 项目。它把自己描述为：

- 基于 LLM Wiki 模式的个人知识库
- Obsidian 为浏览层
- 支持 Claude Code、Codex、Cursor、Gemini CLI 等多种 agent

## 代码与结构观察

关键文件与目录：

- `README.md`
- `docs/REQUIREMENTS.md`
- `skills/`
- `tests/`

从 README 和 `docs/REQUIREMENTS.md` 可以看到：

- 系统围绕 4 个操作组织：onboarding、ingest、query、lint
- 强调 agent config 文件是整个模式的核心
- 使用 wizard 风格进行项目初始化
- 推荐但不强制 `summarize`、`qmd`、`agent-browser`
- 明确把“多 agent 使用同一 vault”当作设计目标之一

## 架构特点

### 优点

- 用户叙事清楚，onboarding 体验好
- agent-agnostic 设计成熟，适合作为 TellMe 的外部沟通参考
- 把“同一规则可被多个宿主共享”表达得很直接
- 把 Karpathy 抽象思路和可执行蓝图之间的桥接写得比较清楚

### 限制

- 本体仍以技能包分发为主，运行时控制面有限
- 更偏向“如何把模式装进 agent”，而不是“如何治理一个长期运行的项目”
- 对增量状态、冲突回收、发布策略等问题没有 TellMe 需要的深度

## 对 TellMe 的启发

- TellMe 的 README、初始化流程和项目叙述方式可以借鉴它的清晰度。
- TellMe 应当把“多 agent 共享一套规则”作为基础预期，而不是高级玩法。
- TellMe 不应只停留在 onboarding 和技能安装层，而应把长期治理能力做深。

## 结论

`second-brain` 适合作为 TellMe 的产品沟通与宿主中立设计参考，但 TellMe 仍然需要比它更强的内部状态管理与发布控制。
