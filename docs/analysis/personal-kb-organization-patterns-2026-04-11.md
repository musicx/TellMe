---
title: Personal Knowledge Base Organization Patterns
date: 2026-04-11
source:
  - /Users/ericliu/Code/repos/llmwiki
  - https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
status: draft
---

# 个人 Knowledge Base 组织形式分析

这份文档只回答一件事：`~/Code/repos/llmwiki/` 里的参考 repo，在 ingest 原始文档之后，最后会把知识沉淀成什么样的 markdown 文档，以及这些文档是怎么分层的。

我重点看的是“存什么”和“怎么组织”，不是实现细节。判断标准主要有四个：

- 原始资料是否保持不可变
- 编译后的知识页分成哪些类型
- 查询、反思、研究输出会不会继续回流成知识
- 系统有没有额外的状态层、审核层或治理层

## Karpathy 的基线模型

Karpathy 在 [llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 里给的是一个模式，不是一个固定 schema。基线很清楚：

- `raw/` 是不可变证据层，放文章、论文、图片、数据文件
- `wiki/` 是 LLM 维护的编译结果层，里面是摘要页、实体页、概念页、比较页、综合页
- `schema` 由 `CLAUDE.md`、`AGENTS.md` 这类规则文件承载，告诉 agent 应该怎么 ingest、query、lint
- `index.md` 是内容目录，`log.md` 是时间线日志
- query 产生的好答案不该留在聊天记录里，而应该继续写回 wiki

换句话说，Karpathy 的核心不是“把文件丢给检索”，而是“把原始资料编译成会不断变厚的知识制品”。

## 先说结论

这 7 个 repo 大致落在 4 种组织路线里：

1. **最小编译器路线**
   `llm-wiki-compiler`
   原始资料保留在 `sources/`，最终知识主要就是 `wiki/concepts/` 和 `wiki/queries/`，结构最轻。

2. **source summary + concept page 双层路线**
   `llm-knowledge-base`、`llm-wiki-plugin`、`second-brain`
   每篇原始资料先落成一个 source/reference 页面，再抽出 concepts、entities、synthesis。

3. **显式 taxonomy 路线**
   `obsidian-wiki`、`llm_wiki_app`
   不只区分 source 和 concept，还会区分 entity、skill、reference、synthesis、query，甚至区分全局知识和项目知识。

4. **运行时和审核层分离路线**
   `obsidian-llm-wiki-local`、`llm_wiki_app`
   最终 wiki 只是发布层，系统还维护草稿、review queue、SQLite 或应用状态，知识不会直接从 raw 一步落到 published。

这几种路线的差别，本质上不在“有没有 wiki”，而在“wiki 前面有没有 staging/state/review”以及“query/research 输出算不算正式知识”。

## 对比表

| Repo | Raw 之后沉淀成什么 | 最终知识目录形态 | 中间层/状态层 | 组织特点 |
| --- | --- | --- | --- | --- |
| `llm-knowledge-base` | source summary、concept page、reflection synthesis、query output | `wiki/sources/`、`wiki/concepts/`、`wiki/archive/`、`outputs/` | `.kb/manifest.json`、`reflect_state.json` | source 和 concept 双层，query/reflection 会回流 |
| `llm-wiki-compiler` | concept page、saved query page | `wiki/concepts/`、`wiki/queries/`、`wiki/index.md` | `.llmwiki/state.json` | 极简编译器，source 不单独变成 wiki 页 |
| `llm-wiki-plugin` | source summary、concept/person page、query page、lint report | `raw/`、`wiki/`、`outputs/reports/` | 插件命令和 qmd 配置 | 更像 Claude 的操作入口层 |
| `llm_wiki_app` | source/entity/concept/query/comparison/synthesis 页面，外加 overview 和 review item | `wiki/sources/`、`wiki/entities/`、`wiki/concepts/`、`wiki/queries/`、`wiki/index.md`、`wiki/log.md`、`wiki/overview.md` | 应用内 review queue、chat state、deep research 流程 | 最接近产品形态，query/research/review 都会写回 wiki |
| `obsidian-llm-wiki-local` | source summary、concept article、draft query | `wiki/` 根目录概念页、`wiki/sources/`、`wiki/queries/`、`wiki/.drafts/` | `.olw/state.db`、`wiki.toml` | 发布前先落 draft，审核边界清楚 |
| `obsidian-wiki` | concepts/entities/skills/references/synthesis/journal 页面，必要时分项目目录 | 全局分类目录 + `projects/<name>/...` | `.manifest.json`、`_raw/` staging | taxonomy 最完整，强调 provenance 和项目/全局两级组织 |
| `second-brain` | source summary、entity page、concept page、synthesis page | `wiki/sources/`、`wiki/entities/`、`wiki/concepts/`、`wiki/synthesis/`、`output/` | 主要靠 schema 和 `wiki/log.md` | 最接近 Karpathy 的通用模板，结构稳但不重 |

## 逐个 repo 看

### `llm-knowledge-base`

这是一个很典型的“先收 raw，再编译成 wiki，再把 query/reflection 继续沉淀”的版本。

- raw 输入按类型分流到 `raw/web/`、`raw/pdfs/`、`raw/images/`、`raw/notes/`
- 每个 raw 文件会先被写成 `wiki/sources/<slug>.md`
- 再从 source summary 里抽出 concepts，写到 `wiki/concepts/<concept>.md`
- `kb-reflect` 会基于现有 `index.md` 找跨页关系，再把结果继续写回 `wiki/concepts/`，只是 frontmatter 里的 `type` 变成 `synthesis`
- `kb-ask` 的回答会落到 `outputs/`，并重新索引回 `wiki/index.md`

它的知识组织有两个明显特点。

第一，它把“来源页”和“知识页”明确分开。`wiki/sources/` 更像证据的结构化摘要，`wiki/concepts/` 才是长期知识节点。第二，它把“反思”和“问答”也当成可持续积累的产物，而不是一次性输出。

这条路线适合 TellMe 参考，因为它已经很接近“知识不是 raw mirror，而是 source-backed compiled artifact”的方向。

### `llm-wiki-compiler`

这是最干净、最克制的一种组织形式。

- ingest 后的原始材料保存在 `sources/`，不是 `raw/`
- compile 之后，主要输出是 `wiki/concepts/<slug>.md`
- query 如果保存，会写成 `wiki/queries/<slug>.md`
- `wiki/index.md` 只汇总 concepts 和 saved queries
- `.llmwiki/state.json` 只管 source hash、concept 归属和 frozen slug，不介入阅读层

它和其他 repo 最大的不同，是**不单独生成 source summary wiki 页**。原始材料仍然保存在 `sources/`，知识页的 provenance 靠两种方式表达：

- frontmatter 里的 `sources: []`
- 正文段落级的 `^[filename.md]` citation

这意味着它把“source page”省掉了，直接把来源关系压进 concept page 自己。好处是结构很轻，坏处是读者视角下不容易把“来源摘要层”和“概念综合层”拆开看。

如果 TellMe 需要一个很薄的 reader-facing layer，这个 repo 值得参考；如果 TellMe 要保留明确的 evidence summary 层，它就不够。

### `llm-wiki-plugin`

这个 repo 更像一个 Claude 插件包装层，核心知识组织并不新，但入口体验更完整。

- 初始化后会创建 `raw/`、`wiki/`、`outputs/reports/`
- compile 会写 source summary、concept page、person page，并更新 index
- query 依赖 qmd 或 `index.md` 检索，结果可以继续写回 wiki
- lint 结果落到 `outputs/reports/`

它的存储模型基本继承 Karpathy 思路，没有走特别重的 taxonomy。重点不在页类型创新，而在“把 wiki 工作流包装成一组稳定命令”，让用户在 Claude Code 里直接跑起来。

所以它更像一个操作壳，不像一个新的知识组织模型。

### `llm_wiki_app`

这是几个 repo 里产品感最强的一个，也是知识层次最丰富的一个。

它保留了 Karpathy 的三层骨架，但往里面加了几层实际运行中很关键的东西：

- `wiki/sources/`：每个来源一页
- `wiki/entities/`：人、组织、工具、项目
- `wiki/concepts/`：概念和理论
- `wiki/queries/`：保存的 chat answer 和 research 结果
- `wiki/index.md`、`wiki/log.md`
- `wiki/overview.md`：对整个 wiki 的总览页
- `purpose.md`：不是知识页，但作为整个 wiki 的“方向约束”
- review queue：人类判断还没做完的事项不会直接混进已发布知识

这个 repo 的关键不是目录多，而是**query/research/review 都是正式知识生产流程的一部分**。

- chat 里值得保留的答案会写入 `wiki/queries/`
- deep research 的结果也会写成 query/research 页，再 auto-ingest 回 concepts/entities 网络
- ingest 不是一步产出，而是 analysis -> generation -> review item

它的 frontmatter 也更像统一 schema，而不是只记 `tags + sources`。常见字段包括 `type`、`title`、`created`、`updated`、`tags`、`related`、`sources`。

如果从“最终存什么”来看，这个 repo 已经不是单纯的 wiki，而是一个把 source、graph、query、review、research 放在同一知识空间里的应用。

### `obsidian-llm-wiki-local`

这个项目是本地 CLI 版本里边界最清楚的一个。

- `raw/` 永远不可写
- `olw ingest` 先分析 note，把摘要和概念写进 `state.db`
- `olw compile` 生成 article，但先落到 `wiki/.drafts/`
- `olw approve` 之后才移动到已发布的 `wiki/`
- `wiki/sources/` 保存 source summary
- 概念页默认放在 `wiki/` 根目录，不再细分 `concepts/` 子目录
- `wiki/queries/` 保存问答页
- `wiki/index.md` 和 `wiki/log.md` 负责导航与日志

它最有价值的地方，是把“知识文档”和“系统状态”彻底分开了。

- markdown 是发布物
- `.olw/state.db` 是运行时真相
- `.drafts/` 是审核中的候选

再加上 frontmatter 里的 `confidence` 和 `status: draft|published`，它天然就比纯技能方案更适合需要审核、回滚和状态查询的系统。

TellMe 如果要保持 compile/staging/publish 的边界，这个 repo 比纯 markdown 方案更值得借鉴。

### `obsidian-wiki`

这是 taxonomy 设计最激进、也最完整的一份。

它不是把知识只分成 source 和 concept，而是分成两层结构：

第一层是**知识类别**：

- `concepts/`
- `entities/`
- `skills/`
- `references/`
- `synthesis/`
- `journal/`

第二层是**项目作用域**：

- 全局知识放在根级分类目录
- 项目知识放在 `projects/<project-name>/<category>/`

它还有几个对 TellMe 很有启发的点。

第一，它把 `references/` 和 `concepts/` 明确拆开了。reference 更接近“来源的结构化摘要”，concept 更接近“脱离单一来源后的知识节点”。第二，它把 provenance 做成一等公民，不只记录 `sources: []`，还允许在正文里标 `^[inferred]` 和 `^[ambiguous]`，并在 frontmatter 里写 `provenance` 比例。第三，它把 `_raw/` 做成 vault 内部的 staging 区，而不是把一切都直接当 published wiki。

如果 TellMe 最终想把 reader-facing 层做得更像“知识地图”，`obsidian-wiki` 的目录分法和 provenance 语义比大多数 repo 都更成熟。

### `second-brain`

`second-brain` 是最像“Karpathy 模板工程化版”的一个。

- `raw/` 是 inbox
- `wiki/sources/` 是来源摘要
- `wiki/entities/` 是人物、组织、工具
- `wiki/concepts/` 是概念、理论、模式
- `wiki/synthesis/` 是比较、分析、主题
- `wiki/index.md` 和 `wiki/log.md` 是固定中枢
- `output/` 放报表和其他生成物

它的 frontmatter 很轻，核心就是 `tags`、`sources`、`created`、`updated`。状态管理也比较轻，更多依赖 schema、skills 和 `wiki/log.md`，不像 `obsidian-llm-wiki-local` 那样有单独数据库。

这个 repo 的优点是通用、稳、容易迁移到不同 agent。缺点也一样明显：一旦知识治理复杂起来，单靠 markdown + log 会显得薄。

## 这些 repo 共同形成了什么模式

如果把这些实现放在一起看，可以看到一个比较稳定的共识。

### 1. 原始资料不是最终知识

没有哪个 repo 真把 `raw/` 当成最后的知识库。最常见的做法是把 raw 继续编译成三类页面：

- **来源页**：`sources/` 或 `references/`
- **节点页**：`concepts/`、`entities/`、有时还有 `skills/`
- **综合页**：`synthesis/`、`queries/`、`comparison`、`overview`

### 2. 最稳的最小单元不是“文件”，而是“页面类型”

这些 repo 真正在组织的不是原始文档集合，而是页面类型集合。用户加进来的是 article、pdf、note，系统沉淀下来的却是：

- 某个来源的摘要页
- 某个概念的长期页
- 某个实体的长期页
- 某次 query 的高价值答案页
- 某次 reflection 或 research 的综合页

### 3. `index.md` 和 `log.md` 几乎是默认标配

不管是否有数据库、是否有 qmd、是否有 graph view，`index.md` 和 `log.md` 基本都在。它们分别解决两个问题：

- `index.md` 解决“LLM 和人类怎么低成本找到页”
- `log.md` 解决“系统最近做过什么、哪些 source 已处理”

### 4. query output 越来越像正式知识，而不是聊天副产物

Karpathy 在概念上强调过这一点，几个实现也都在往这边走：

- `llm-knowledge-base` 会把答案索引回 wiki
- `llm-wiki-compiler` 有 `wiki/queries/`
- `llm_wiki_app` 会把 saved answer 和 deep research 继续 auto-ingest
- `second-brain` 直接把 synthesis 当成正式目录

这说明一个很重要的趋势：personal knowledge base 不再只吸收“外部原始资料”，也吸收“你与系统一起做出的中间思考成果”。

### 5. 真正成熟的实现，都会把状态层从内容层里抽出来

前面几个轻量 repo 主要靠 manifest、index、log。再往前走，就会出现：

- SQLite 状态库
- draft/review 队列
- content hash
- publish/approve 边界
- review item 和 health finding

这一步很关键，因为一旦系统开始支持 merge、contradiction、query filing、deep research、human approval，单靠 published markdown 已经不够表达状态了。

## 对 TellMe 最明确的启发

如果只从“知识最终该长什么样”这个问题出发，我会给 TellMe 一个很明确的结论。

TellMe 不该把 ingest 的结果停在 `source summary`，也不该只停在 `concept/entity` 平铺页。更合理的目标形态应该至少有 4 层：

1. **证据层**
   `raw/`，保持不可变。

2. **候选层**
   `staging/`，承接 graph candidate、query candidate、health finding、conflict explanation。

3. **状态层**
   `state/` 和 `runs/`，记录 source hash、candidate status、publish decision、host output、review queue。

4. **发布层**
   `vault/`，面向 Obsidian 和读者，至少要能容纳 `references/`、`themes/`、`subthemes/`、reader-facing synthesis/query/output 页面。

从这些参考 repo 看，TellMe 已经在往这个方向走了，而且方向是对的。它和参考实现真正不同的地方，不该是“也能生成 concept page”，而该是：

- graph candidate 和 reader-facing page 明确分层
- query/output/health result 都能作为正式候选回流
- published vault 不是状态数据库，只是阅读界面
- 宿主直接修改之后还能通过 reconcile 回收

如果再收一句，这批参考 repo 共同说明了一件事：个人 knowledge base 最终存下来的，不应该是“原文副本”，而应该是**来源页、知识节点页、综合页、审核页和运行状态一起组成的编译产物系统**。区别只在于，有的 repo 只做到前两层，有的已经把后面三层也做出来了。
