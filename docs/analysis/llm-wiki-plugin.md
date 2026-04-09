# `llm-wiki-plugin` 技术分析

## 项目定位

`llm-wiki-plugin` 是一个 Claude 插件，目标是把 LLM Wiki 的常用操作封装成单一插件入口。

用户通过如下风格的命令使用它：

- `wiki init`
- `wiki ingest`
- `wiki compile`
- `wiki query`
- `wiki lint`
- `wiki remove`

## 代码与结构观察

仓库包含：

- `.claude-plugin/`
- `commands/wiki.md`
- `hooks/`
- `scripts/`
- `skills/`

`commands/wiki.md` 只做一件事：把用户输入路由到 `llm-wiki:wiki` 技能，说明插件作者把“单命令入口 + 技能后端”视为主要交互模式。

README 中还明确了几个实现约束：

- 依赖 Node.js 18+
- 依赖 Git
- 默认假设 Obsidian vault 在 `~/ObsidianVault/03-Resources/`
- 第一次会自动安装 `qmd` 和 `marp-cli`

## 架构特点

### 优点

- 命令面非常清晰，入口语义统一
- 明确把 qmd 作为可选或自动启用的搜索增强
- 支持 query、lint、remove 这些完整生命周期动作
- 对 Obsidian 资源目录有明确约定，上手成本低

### 限制

- 适配面明显偏向 Claude 插件生态
- 路径约定偏硬编码，不适合 PC/Mac 间切换
- 插件视角下的状态管理较薄
- 多宿主共享同一知识库的策略并不明显

## 对 TellMe 的启发

- TellMe 应该保留统一命令语义，而不是为不同宿主发明不同动作名。
- `qmd`、`Marp` 这类外部工具适合作为策略层的可选增强，而不是核心必需。
- TellMe 不能把 vault 位置写死，必须通过 `config/machines/*.toml` 做路径映射。

## 结论

`llm-wiki-plugin` 的价值在于交互面整洁、指令路由统一，但它本身不足以支撑 TellMe 需要的跨宿主、跨机器和可追溯状态管理。
