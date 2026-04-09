# `obsidian-llm-wiki-local` 技术分析

## 项目定位

`obsidian-llm-wiki-local` 是 5 个参考实现里最接近“独立产品”的一个。它不是技能集合，而是一个 Python CLI：

- 包名：`obsidian-llm-wiki`
- 命令名：`olw`
- 运行模型：本地 Ollama

它的目标是把 `raw/` 中的笔记经由本地 LLM 编译成可发布 wiki，并提供草稿审批、查询、lint、watch 等完整流程。

## 代码与结构观察

关键文件与目录：

- `pyproject.toml`
- `install.py`
- `src/obsidian_llm_wiki/`
- `tests/`
- `CLAUDE.md`

从 `pyproject.toml` 和 `cli.py` 可见：

- 使用 Python 3.11+
- 依赖 `click`、`rich`、`pydantic`、`httpx`、`watchdog`、`python-frontmatter`
- 提供命令：`init`、`setup`、`ingest`、`compile`、`approve`、`reject`、`status`、`undo`、`clean`、`doctor`、`query`、`lint`、`watch`

从 `config.py` 和 `CLAUDE.md` 可见：

- 同时存在用户级配置和项目级配置
- 项目级配置写在 `wiki.toml`
- 使用 `.olw/state.db` 作为 SQLite 状态库
- 使用 `wiki/.drafts/` 作为显式审核区
- 使用原子写和内容哈希规避崩溃与手工编辑覆盖

## 架构特点

### 优点

- 明确的 CLI 控制面，接近 TellMe 需要的正式命令体验
- 项目内有显式状态库，而不是完全依赖 markdown 文件结构
- 草稿审批和发布边界清晰
- 有 watcher、doctor、undo 等工程化命令
- 测试比较完整，说明作者把稳定性当作产品问题而非提示词问题

### 限制

- 核心假设是“全部使用本地 Ollama”，对多宿主、多模型路由考虑较少
- 它的重点是单机本地运行，而不是 `Claude Code` / `Codex` / `OpenCode` 混合编排
- 项目把 vault 本身当成几乎完整的工作目录，没有再拆出独立的 `state/`、`runs/`、`staging/` 控制面
- 没有针对 TellMe 目标中最重要的 `reconcile` 做一等公民设计

## 对 TellMe 的启发

- TellMe 的 Python 核心、TOML 配置、状态持久化、草稿工作流，最适合从它的方向演进。
- TellMe 应该把它的 `approve` 思路升级为“风险分级发布策略”。
- TellMe 应该把 `.olw/state.db` 这种状态层扩展成更清晰的 `state/` 和 `runs/` 分层。
- TellMe 不应复制它的 Ollama-only 假设，而应把模型选择抽象到宿主与策略层。

## 结论

这是 TellMe 最重要的工程参考。TellMe 的产品骨架应当更接近它，而不是纯技能包方案。但 TellMe 需要继续往多宿主编排和 reconcile 方向扩展。
