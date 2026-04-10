# TellMe 项目设计文档

## 1. 项目目标

TellMe 是一个基于 Obsidian 展示层的 LLM-wiki 编排系统。它的核心目标不是“回答问题”，而是把原始资料持续编译为结构化、可链接、可追溯、可维护的 wiki，并允许多个 AI 宿主共同参与这一过程。

TellMe 的一版设计目标：

- 使用 Python 构建跨平台本地核心
- 在 PC 和 MacBook 上通过配置映射同一项目结构
- 允许 `Claude Code`、`Codex`、`OpenCode` 作为宿主接入
- 把 `Obsidian` 限定为展示与浏览层
- 通过正式状态层和 `reconcile` 机制治理宿主直接修改

## 2. 设计结论

TellMe 采用混合方案：

- 有自己的本地编排核心
- 有自己的项目状态和运行记录
- 同时向多个宿主暴露统一的入口协议

硬约束如下：

- TellMe 项目根目录是真实控制面
- `vault/` 只是面向 Obsidian 的发布目录，不是完整系统状态

## 3. MVP 范围

第一版只把以下 6 个动作做成正式命令：

- `tellme init`
- `tellme ingest`
- `tellme compile`
- `tellme query`
- `tellme lint`
- `tellme reconcile`

其中 `compile`、`query`、`reconcile` 是 TellMe 与多数参考实现拉开差异的关键。

## 4. 核心原则

### 4.1 编译优先，而不是即时检索优先

TellMe 不把原始资料只当作 RAG 素材库，而是把它们编译进 wiki。查询动作优先基于已发布知识层完成，必要时才回看 source summary 或原始资料。

### 4.2 宿主只是入口，不是系统真相来源

不论是 Claude Code、Codex 还是 OpenCode，宿主都只是在调用同一项目。TellMe 不应把任何宿主目录、全局技能目录或对话历史视为唯一控制面。

### 4.3 Obsidian 只是展示层

Obsidian 负责：

- 浏览 Markdown
- 展示 backlinks 与 graph
- 运行 Dataview 等阅读层插件

Obsidian 不负责：

- 编排 ingest / compile / publish
- 保存内部状态库
- 替代运行日志与 reconcile

### 4.4 允许直接修改，但必须可回收

TellMe 接受一个现实：不同宿主会直接修改 `vault/`。因此它必须显式支持 `reconcile`，而不是寄希望于所有宿主都严格走标准管线。

## 5. 系统架构

TellMe 由 5 个核心子系统组成：

### 5.1 Core CLI

负责 6 个正式命令，是用户和宿主都能依赖的稳定入口。

### 5.2 Project Runtime

负责读写：

- `config/`
- `state/`
- `runs/`
- `staging/`

它维护 manifest、哈希、页面元数据、发布状态、风险策略和 reconcile 状态。

### 5.3 Host Adapter Layer

为 `Claude Code`、`Codex`、`OpenCode` 生成宿主约束与上下文文件，并把统一语义映射到各宿主。

### 5.4 Content Pipeline

负责从 `raw/` 到 `staging/` 再到 `vault/` 的内容生命周期。

### 5.5 Vault Publisher

把通过策略筛选的内容发布到 `vault/`，保证 Obsidian 看到的是已发布知识，而不是中间态。

## 6. 项目目录

建议目录如下：

```text
TellMe/
├── config/
│   ├── project.toml
│   ├── hosts/
│   ├── machines/
│   └── policies/
├── docs/
├── hosts/
├── raw/
├── runs/
├── staging/
├── state/
├── templates/
└── vault/
```

### 目录职责

- `config/`: 项目、宿主、机器、策略配置
- `raw/`: 原始资料，不允许 LLM 改写
- `staging/`: 草稿区和候选更新
- `state/`: manifest、哈希、页面状态、对账状态
- `runs/`: 每次正式运行的日志、产物和审计记录
- `vault/`: 发布后的 wiki 内容，供 Obsidian 打开
- `hosts/`: 宿主上下文模板或未来生成产物
- `templates/`: 页面模板、提示词模板、frontmatter 模板

## 7. 内容生命周期

TellMe 中每一份内容都应显式处于以下状态链之一：

`raw -> registered -> analyzed -> staged -> published -> reconciled`

### 状态定义

- `raw`: 原始资料落盘
- `registered`: 已进入 manifest，拥有来源和 hash
- `analyzed`: 已抽取出摘要、概念、实体、风险
- `staged`: 已生成候选页面或候选更新
- `published`: 已通过发布策略并进入 `vault/`
- `reconciled`: 宿主直接修改后的差异已被 TellMe 吸收

## 8. 发布策略

TellMe 采用混合发布策略：

- 低风险更新可直接发布到 `vault/`
- 高风险更新先进入 `staging/`

高风险因素包括但不限于：

- 新建跨领域 synthesis 页面
- 缺少足够 source attribution
- 会覆盖人工编辑痕迹
- 会影响大量 backlinks 或索引结构

## 9. Reconcile 设计

`tellme reconcile` 是 TellMe 的正式一等命令，用于处理宿主直接修改。

### 9.1 目标

- 扫描 `vault/` 变化
- 识别人工修改与自动修改的差异
- 更新 `state/` 中的页面 hash、元数据、链接图
- 必要时把冲突页面退回 `staging/`

### 9.2 约束

- 不允许静默覆盖人工修改
- 冲突默认保留人工版本
- 系统只能生成 merge candidate，不可直接强推回滚

## 10. 配置模型

TellMe 使用 TOML，并采用分层配置：

- `config/project.toml`: 项目级真相来源
- `config/hosts/*.toml`: 宿主适配覆盖
- `config/machines/*.toml`: 机器路径覆盖
- `config/policies/*.toml`: 模型、发布、reconcile 策略

### 10.1 为什么要分层

- 同一项目要在 PC 与 MacBook 上运行，路径映射不同
- 同一项目要在 3 个宿主中运行，工作模式不同
- 同一项目要根据任务类型路由不同模型或不同宿主

### 10.2 路径策略

项目只声明逻辑路径，例如 `primary_vault`。实际物理路径由机器配置负责映射：

- Windows: `E:\Code\Home\AI\TellMe\vault`
- macOS: `/Users/.../Home/AI/TellMe/vault`

## 11. 宿主适配策略

### 11.1 Claude Code

适合长流程编排、复杂 compile、深度 query、lint 和批量 reconcile。

### 11.2 Codex

适合结构化修改、配置更新、规则文件维护、批量修订和工程化操作。

### 11.3 OpenCode

适合轻量入口、日常 ingest、快速 query、快速草稿生成。

### 11.4 统一要求

三个宿主必须共享同一组正式命令语义，而不是各自发明新动作。

## 12. 页面与元数据约束

TellMe 中的 wiki 页面至少需要：

- 页面类型
- 来源引用
- 创建时间
- 更新时间
- 最后生成宿主
- 发布状态

未来可扩展：

- 风险等级
- 人工编辑标记
- 可信度
- 关联 run id

## 13. 参考实现吸收策略

### 采纳

- `obsidian-llm-wiki-local`: Python CLI、配置、状态库、草稿审批
- `obsidian-wiki`: 多宿主 bootstrap 与技能分发思路
- `second-brain`: onboarding 和 agent-agnostic 叙事
- `llm-knowledge-base`: compile / reflect / lint 的完整生命周期
- `llm-wiki-plugin`: 单入口命令与可选搜索工具集成思路

### 不采纳

- 单一宿主强绑定
- 写死 vault 位置
- 把项目真相来源放在用户主目录
- 完全依赖 prompt 约束而缺少显式状态控制

## 14. 风险与后续议题

### 当前已知风险

- 多宿主并发写入时需要锁或运行序列化策略
- 页面级 source attribution 细粒度设计仍待细化
- `query` 回写的风险分类还需规则化
- `reconcile` 的差异检测粒度需要在实现阶段验证

### 下一阶段建议

- 落 Python 包结构与 CLI 骨架
- 定义 `state/` 下的数据模型
- 定义 `runs/` 目录的文件格式
- 定义最小 frontmatter schema
- 生成 `Claude Code`、`Codex`、`OpenCode` 的宿主模板

## 15. 当前结论

TellMe 不应是纯技能包，也不应把 Obsidian 当作系统本体。它应该是一个有本地运行时、有多宿主入口、有显式发布策略、并且把 `reconcile` 当作核心能力的混合式 LLM-wiki 编排器。
