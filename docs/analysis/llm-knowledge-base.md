# `llm-knowledge-base` 技术分析

## 项目定位

`llm-knowledge-base` 是一个面向 Claude Code 的知识库工作流项目。核心思路是：

- 使用 Obsidian 作为 wiki 浏览器。
- 使用 Claude Code 技能驱动 ingest、compile、ask、reflect、lint、merge。
- 使用一个独立的 Python 搜索脚本补足检索能力。

它更像“完整的 Claude 工作流包”，而不是通用运行时。

## 代码与结构观察

仓库关键文件包括：

- `skills/`：`kb-ingest`、`kb-compile`、`kb-ask`、`kb-reflect`、`kb-lint`、`kb-merge` 等技能
- `kb_search.py`：本地搜索 CLI
- `setup.sh`：初始化知识库目录并写入 `~/.claude/kb-config.json`
- `requirements.txt`：可选 Python 依赖

`kb_search.py` 的实现说明了几个具体技术点：

- 配置来源于用户主目录下的 `~/.claude/kb-config.json`
- 对 `wiki/concepts` 和 `wiki/sources` 建索引
- 同时支持关键词 TF-IDF 和可选 sentence-transformers 语义检索
- 构建结果写到 `.kb/search_index.json`

## 架构特点

### 优点

- 生命周期完整：`ingest -> compile -> reflect -> ask -> lint -> merge`
- 反思机制明确：`reflect` 会自动从 index 中寻找新的综合主题
- 用 `index.md` 作为轻量路由层，避免强依赖向量库
- 搜索脚本是独立可替换模块，不把检索能力绑死在宿主里

### 限制

- 强依赖 Claude Code 和 `~/.claude/` 全局配置
- 项目状态并不完全在项目根目录内，跨机器可移植性一般
- 没有显式的多宿主对齐机制
- 缺少针对“人工直接改 vault 后”的 reconcile 设计

## 对 TellMe 的启发

- TellMe 可以借鉴它的生命周期分层，尤其是 `reflect` 和 `merge` 的扩展视角。
- TellMe 不应复制它的全局配置模式，而应让项目根目录包含完整配置真相。
- TellMe 可以保留“轻量索引优先，外部检索为可选增强”的策略。

## 结论

`llm-knowledge-base` 证明了 LLM-wiki 不该只有 ingest 和 query，还需要 compile、reflect、lint、merge 等维护动作。但它的宿主和配置方式过于偏 Claude，不能直接作为 TellMe 的产品骨架。
