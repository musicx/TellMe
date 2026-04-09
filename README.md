# TellMe

TellMe 是一个以 Obsidian 为展示层、以 Python 编排核心为控制面的 LLM-wiki 项目骨架。

项目目标不是做一个单纯的 RAG 包装器，而是把原始资料持续编译为可累积、可维护、可追溯的 Markdown wiki。`Obsidian` 负责阅读、导航、图谱和插件生态；`TellMe` 负责项目状态、运行日志、发布策略、宿主适配和内容对账。

## 当前状态

当前仓库处于设计与项目骨架阶段，已经落地了：

- 项目约束文档 `AGENTS.md`
- 参考实现技术分析文档 `docs/analysis/`
- TellMe 设计文档 `docs/tellme-design.md`
- 跨平台与多宿主配置骨架 `config/`

后续实现将围绕以下 6 个正式命令展开：

- `tellme init`
- `tellme ingest`
- `tellme compile`
- `tellme query`
- `tellme lint`
- `tellme reconcile`

## 设计原则

- `TellMe` 项目根目录是真实控制面，`vault/` 不是全部系统状态。
- `Obsidian` 是展示层，不是编排器。
- `Claude Code`、`Codex`、`OpenCode` 是三种宿主入口，不是三套独立实现。
- 允许宿主绕过标准流程直接修改内容，但必须由 `reconcile` 把系统拉回一致状态。
- 内容发布采用混合策略：低风险变更可直接发布，高风险变更先进入 `staging/`。

## 目录概览

```text
TellMe/
├── AGENTS.md
├── README.md
├── config/
│   ├── project.toml
│   ├── hosts/
│   ├── machines/
│   └── policies/
├── docs/
│   ├── analysis/
│   └── tellme-design.md
├── hosts/
├── raw/
├── runs/
├── staging/
├── state/
├── templates/
└── vault/
```

## 建议阅读顺序

1. `docs/tellme-design.md`
2. `docs/analysis/overview.md`
3. `config/project.toml`
4. `AGENTS.md`

## 参考来源

TellMe 的设计直接参考了 `E:\Code\git\genai-related\llm-wiki\` 下的 5 个实现：

- `llm-knowledge-base`
- `llm-wiki-plugin`
- `obsidian-llm-wiki-local`
- `obsidian-wiki`
- `second-brain`

每个项目的具体技术分析见 `docs/analysis/`。
