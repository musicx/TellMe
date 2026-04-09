# `obsidian-wiki` 技术分析

## 项目定位

`obsidian-wiki` 的核心思想是：不要先做运行时，而是先做一个对多种 AI agent 都能消费的技能框架。

它支持的宿主范围非常广，包括：

- Claude Code
- Cursor
- Windsurf
- Codex
- Gemini / Antigravity
- OpenClaw
- GitHub Copilot

## 代码与结构观察

关键文件与目录：

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.skills/`
- `setup.sh`
- `.env.example`

从 `setup.sh` 可见：

- 用 `.env` 中的 `OBSIDIAN_VAULT_PATH` 配置 vault
- 把 `.skills/*` symlink 到多种宿主的技能目录
- 既安装工作区内技能，也安装全局技能
- 明确包含 `~/.codex/skills/` 和 `~/.agents/skills/`，说明它已经把 Codex 与通用 AGENTS 宿主作为一等目标

从 `AGENTS.md` 可见：

- 宿主通过读取 `.manifest.json`、`index.md`、`log.md` 和技能目录来执行操作
- 核心规则是“编译知识，不要简单检索”
- 技能语义完整，包括 setup、ingest、query、lint、rebuild、cross-link、tag-taxonomy、update

## 架构特点

### 优点

- 多宿主兼容性是 5 个项目里最强的一类
- 技能语义丰富，覆盖 ingest、query、lint、rebuild、taxonomy 等实际治理需求
- bootstrap 非常完整，降低了不同 agent 间切换成本
- 对项目组织、标签规范、知识治理的关注度较高

### 限制

- 运行时非常薄，大量一致性依赖宿主遵守技能说明
- `.manifest.json`、index、log` 是重要状态，但没有看到更强的事务型控制面
- 当多个宿主同时工作时，系统缺少显式的冲突吸收和 reconcile 策略
- 更适合作为“可执行规范层”，而不是 TellMe 的全部实现

## 对 TellMe 的启发

- TellMe 必须吸收它的多宿主 bootstrap 经验。
- TellMe 的 `hosts/` 和 `config/hosts/` 就应该参考它的“同一语义、多宿主分发”的做法。
- TellMe 不应停留在纯技能框架，而要在其上叠加正式运行时和状态层。

## 结论

`obsidian-wiki` 是 TellMe 的宿主适配参考样板，但不是运行时样板。TellMe 应该在它的多宿主思路之上，增加 Python 核心和 reconcile。
