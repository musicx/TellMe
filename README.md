# TellMe

TellMe 是一个以 Obsidian 为展示层、以 Python 编排核心为控制面的 LLM-wiki 项目骨架。

项目目标不是做一个单纯的 RAG 包装器，而是把原始资料持续编译为可累积、可维护、可追溯的 Markdown wiki。`Obsidian` 负责阅读、导航、图谱和插件生态；`TellMe` 负责项目状态、运行日志、发布策略、宿主适配和内容对账。

## 当前状态

当前仓库处于本地 orchestrator V1 阶段，已经落地了：

- 项目约束文档 `AGENTS.md`
- 参考实现技术分析文档 `docs/analysis/`
- TellMe 设计文档 `docs/designs/2026-04-09-tellme-intital-design.md`
- 跨平台与多宿主配置骨架 `config/`
- Python CLI 与文件型 `state/runs` 数据模型
- 无 LLM 依赖的 `ingest`、`compile`、`query`、`lint`、`reconcile` V1 工作流

当前 6 个正式命令都有 V1 行为：

- `tellme init`
- `tellme ingest`
- `tellme compile`
- `tellme query`
- `tellme lint`
- `tellme reconcile`

当前限制：

- `compile` 只生成带来源引用的 deterministic source summary 页面，不做 LLM synthesis。
- `query` 只做 vault-first keyword context collection，并写入 run artifact；不会直接调用模型生成最终答案。
- `Claude Code`、`Codex`、`OpenCode` 目前通过 `--host` 身份和 host task JSON 协议接入，还没有自动调用宿主 CLI。

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
│   └── designs/
├── hosts/
├── raw/
├── runs/
├── staging/
├── state/
├── templates/
└── vault/
```

## 建议阅读顺序

1. `docs/designs/2026-04-09-tellme-intital-design.md`
2. `docs/analysis/overview.md`
3. `config/project.toml`
4. `AGENTS.md`

## 开发验证

当前最小测试集：

```powershell
python -m pytest tests -q
```

未安装包时，可用源码路径运行 CLI：

```powershell
$env:PYTHONPATH = "src"
python -m tellme --help
python -m tellme init .\scratch\TellMe --machine windows-dev
```

## 最小使用流程

```powershell
$env:PYTHONPATH = "src"

# 1. 初始化项目
python -m tellme init .\scratch\TellMe --machine windows-dev

# 2. 注册原始资料，外部文件会复制到 raw/
python -m tellme --project .\scratch\TellMe ingest E:\path\to\source.md

# 3. 编译为 Obsidian 可浏览页面
python -m tellme --project .\scratch\TellMe compile

# 4. 基于 vault/ 已发布内容查询，并把结果写入 runs/<run-id>/artifacts/
python -m tellme --project .\scratch\TellMe query "你的问题"

# 5. 如果希望把 query 结果变成候选内容，先进入 staging/queries/，不会自动发布
python -m tellme --project .\scratch\TellMe query "你的问题" --stage

# 6. 检查 vault 静态结构
python -m tellme --project .\scratch\TellMe lint

# 7. 吸收人工或宿主直接修改过的 vault 页面 hash
python -m tellme --project .\scratch\TellMe reconcile
```

多宿主身份可通过 `--host` 指定：

```powershell
python -m tellme --project .\scratch\TellMe --host claude-code compile
python -m tellme --project .\scratch\TellMe --host codex query "问题"
python -m tellme --project .\scratch\TellMe --host opencode ingest .\note.md
```

## 参考来源

TellMe 的设计直接参考了 `E:\Code\git\genai-related\llm-wiki\` 下的 5 个实现：

- `llm-knowledge-base`
- `llm-wiki-plugin`
- `obsidian-llm-wiki-local`
- `obsidian-wiki`
- `second-brain`

每个项目的具体技术分析见 `docs/analysis/`。
