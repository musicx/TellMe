---
title: TellMe Prompt Readability Comparison
date: 2026-04-12
source:
  - /Users/ericliu/Code/projects/TellMe/src/tellme
  - /Users/ericliu/Code/repos/llmwiki
status: draft
---

# TellMe 与参考项目的 Prompt 对比

这份文档只看一件事：TellMe 现在用于抽取概念、主题和 reader-facing 内容的 prompt，和参考项目里同类 prompt 相比，为什么更偏结构化、更偏治理，却还不够利于最后 `wiki/` 目录里的页面可读性。

这里说的“prompt”不只包括直接喂给模型的 system prompt，也包括 TellMe 现在生成给 Codex/宿主的 handoff markdown。因为在 TellMe 里，很多关键约束就是通过 handoff 文本表达的。

## 先说结论

TellMe 现在的 prompt 体系很强的一点，是**状态边界清楚、输出 schema 清楚、可验证性强**。但它有三个明显短板：

1. **抽取 prompt 强，写作 prompt 弱**
   TellMe 很强调节点、claim、relation、conflict 的结构化抽取，却没有给“最后页面应该怎么读起来像一篇给人看的 wiki 页面”同等强度的写作约束。

2. **图谱导向强，读者导向弱**
   它更像在要求模型产出可入库的 graph candidate，不像在要求模型写出一篇能带着读者走完一个主题的页面。

3. **reader rewrite 太后置，而且目标太模糊**
   当前 reader rewrite prompt 只说“读起来自然一些”，但没有定义什么叫自然、什么叫可读、什么叫好的主题页、概览页、参考页。

所以现在 TellMe 更容易产出：

- 节点摘要
- claim 清单
- 关系清单
- 证据列表

但不太容易稳定产出：

- 有明确开场和中心问题的概览页
- 有叙事顺序的 theme/subtheme 页面
- 既精确又好读的 reference 页面
- 既保留来源又不显得像数据库导出结果的内容

## TellMe 现在到底在怎么提示模型

## 1. Codex compile handoff 主要在要求“结构化 graph candidate”

TellMe 现在最核心的抽取提示在 [`src/tellme/codex.py`](/Users/ericliu/Code/projects/TellMe/src/tellme/codex.py)。它的目标很明确：

- 从 source 里抽 concepts、claims、relations、conflicts
- 和已有 `wiki/` 图谱页对照
- 输出 JSON candidate
- 节点字段必须包含 `id`、`kind`、`title`、`summary`、`sources`

这套 prompt 的优点是可靠，也很适合做 staged graph pipeline。问题是，它的产物不是文章，而是**知识图谱更新包**。

这会直接影响可读性，因为模型在这里被训练成回答这类问题：

- 这个节点是什么
- 这条 claim 是什么
- 这条 relation 是什么
- 这条 conflict 怎么挂进去

而不是这些问题：

- 读者第一次打开这个主题页时最该先理解什么
- 这一页的主线是什么
- 哪些细节该放正文，哪些该退到 evidence
- 这一页和相邻页面之间应该怎样组织阅读顺序

换句话说，TellMe 现在把“知识编译”理解得更像**结构化抽取**，不是**解释性写作**。

## 2. graph candidate 投影页本身也偏“记录表”

在 [`src/tellme/graph.py`](/Users/ericliu/Code/projects/TellMe/src/tellme/graph.py) 里，TellMe 把候选节点落成 markdown 时，页面结构基本是：

- 标题
- 一段 `summary`
- `## Claims`
- `## Relations`
- `## Evidence`

这套格式适合 review，适合核查，适合后续再加工，但它不太像最终给人读的 wiki 页面。

它的问题不在“有 claims 和 evidence”，而在于页面主要由以下几类句子组成：

- 节点摘要句
- claim 列表句
- relation 列表句
- source 列表句

缺少的是：

- 这页为什么存在
- 这页和上一级主题的关系
- 什么是核心，什么是补充
- 如果读者只看一分钟，应该记住什么

所以 TellMe 当前的默认页面形态更像“审阅卡片”，不是“解释页面”。

## 3. health handoff 更像知识治理 prompt，不是内容增强 prompt

[`src/tellme/health.py`](/Users/ericliu/Code/projects/TellMe/src/tellme/health.py) 里的 health reflection prompt 主要在要求：

- 找薄弱节点
- 找弱链接
- 找重复概念
- 找冲突
- 按固定 finding schema 输出

这对系统治理很重要，但它几乎不问：

- 哪些页面虽然结构完整，但读起来仍然生硬
- 哪些主题页只有 claim，没有解释
- 哪些 reference 页虽然准确，但缺少“如何理解它”的段落
- 哪些 page 的摘要能索引，但不能引导阅读

也就是说，TellMe 的 health prompt 今天关注的是**知识完整性**，不是**阅读质量**。

## 4. reader rewrite handoff 目标太宽，写法太空

[`src/tellme/reader_rewrite.py`](/Users/ericliu/Code/projects/TellMe/src/tellme/reader_rewrite.py) 现在的核心目标句是：

- “Rewrite existing reader-facing pages so they read more naturally while preserving source traceability and page role boundaries.”

这句话方向没错，但太宽了。它没有告诉模型：

- 概览页应该像目录前言，而不是摘要拼贴
- 主题页应该像章节，不是节点汇总
- subtheme 页应该承担什么阅读任务
- reference 页应该多短、多准、多像定义页
- “more naturally” 具体要避免哪些坏味道

结果就是 rewrite 很容易沦为局部润色，而不是结构性改写。

## 参考项目是怎么做的

## 1. `llm-wiki-compiler`：抽取 prompt 很轻，但 page prompt 明确在写“wiki page”

[`llm-wiki-compiler/src/compiler/prompts.ts`](/Users/ericliu/Code/repos/llmwiki/llm-wiki-compiler/src/compiler/prompts.ts) 很有代表性。

它的 extraction prompt 很轻，只要求模型识别 3 到 8 个有意义的概念。真正关键的是 page generation prompt：

- “You are a wiki author.”
- “Write a clear, well-structured markdown page”
- “Write in a neutral, informative tone”
- “Be concise but thorough”
- 可以参考 existing page 和 related pages
- 要在段落末尾做 citation

这里的重点不是字段，而是**作者角色**。模型被要求扮演的是一个会写页面的人，而不是一个会产出 graph patch 的抽取器。

TellMe 当前在这一步上的缺口很明显：它有“candidate schema”，但没有同等强度的“page authoring contract”。

## 2. `llm_wiki_app`：两阶段 prompt 明确区分分析和写作

`llm_wiki_app` 是对 TellMe 最有参考价值的一份。

在 [`llm_wiki_app/src/lib/ingest.ts`](/Users/ericliu/Code/repos/llmwiki/llm_wiki_app/src/lib/ingest.ts) 里，它先跑 analysis prompt，再跑 generation prompt。

analysis prompt 会要求模型先回答：

- key entities
- key concepts
- main arguments and findings
- connections to existing wiki
- contradictions and tensions
- recommendations

generation prompt 再要求：

- 生成 source page、entity page、concept page、index、log、overview
- frontmatter 结构
- review item 结构
- 当前 wiki purpose、schema、index、overview 都作为上下文输入

这里最关键的不是“字段更多”，而是**它先让模型想清楚，再让模型下笔**。而且它让模型显式考虑：

- 什么该强调
- 什么该弱化
- 它和现有 wiki 的关系
- 整个 wiki 的 overview 要怎么更新

TellMe 现在 compile handoff 里虽然也有 existing graph nodes，但没有这一层“分析结论先行”的写作中介层。于是模型更容易直接输出抽取结果，而不是消化后的 reader-facing 内容。

## 3. `obsidian-wiki`：把“怎么让页面可读”写成了 schema

`obsidian-wiki` 并没有一个集中式 system prompt 文件，但它的 `llm-wiki` 和 `wiki-ingest` skill 把写作规则写得很细。

关键点有几个：

- 页面有 `summary:` frontmatter，而且明确说明这是“没打开页面之前给读者看的 1 到 2 句预览”
- 页面分 category、project scope、global scope
- 需要主动做 cross-reference
- 要区分 extracted、inferred、ambiguous
- project overview、global concept、reference、synthesis 各自承担不同阅读职责

这套规则会逼着模型写出一种“有阅读任务分工”的页面集合。

TellMe 现在虽然也有 theme/subtheme/reference 这些 reader-facing 角色，但大部分约束还停留在发布层代码里，没有强到 prompt 里。模型拿到的不是“页面职责”，而是“字段和值”。

## 4. `second-brain` 和 `llm-knowledge-base`：更像“编辑流程”

这两个项目的 prompt/skill 一个共同点很重要：它们会直接要求模型写这些东西。

`second-brain-ingest`：

- 先做 source summary
- summary 里要有 key claims、entities、concepts
- 再更新 entity / concept page
- source summary 只保留事实，解释和综合放到 concept/synthesis

`llm-knowledge-base/kb-compile`：

- 先写 source summary
- 再写 concept article
- 明确要求 concept article 是“standalone reference”
- 要定义概念、解释为什么重要、描述怎么运作、说明变体和相关想法

`kb-reflect` 更进一步，它要求 synthesis article：

- 解释 connection / contradiction / gap
- 说明为什么重要
- 让读者没看过原始 source 也能读懂

这些 prompt 有一个共同点：**它们默认最终交付物就是文章**。TellMe 当前默认最终交付物更像“待发布知识对象”。

## 差异到底在哪里

把 TellMe 和参考项目并排看，差异主要有六条。

## 1. TellMe 先问“怎么入库”，参考项目先问“这一页怎么写”

TellMe 当前 prompt 最强的部分是：

- source 是否合规
- candidate 字段是否齐全
- page_type 是否正确
- 这条记录挂在哪个 state 节点下

参考项目更强的部分是：

- 这一页是不是 standalone
- 第一段是不是能解释清楚
- 该定义什么、比较什么、链接什么
- 哪些内容应该在 source page，哪些应该在 synthesis page

这就导致 TellMe 的内容更“规整”，参考项目的内容更“像文章”。

## 2. TellMe 缺“页面角色 prompt”，只有“页面路径 prompt”

TellMe 的 reader-facing 路径已经不少了：

- `wiki/index.md`
- `wiki/themes/*.md`
- `wiki/subthemes/*.md`
- `wiki/references/*.md`

但当前 handoff prompt 并没有分别告诉模型：

- overview 页的目标是什么
- theme 页的目标是什么
- subtheme 页的目标是什么
- reference 页的目标是什么

参考项目，尤其是 `obsidian-wiki`，会把角色边界讲清楚。TellMe 现在更多是靠 `page_type` 和生成代码默认结构兜底。

## 3. TellMe 对“语气”和“叙事”约束太少

参考项目会直接写：

- neutral, informative tone
- concise but thorough
- standalone reference
- write for a reader who has not read the source
- overview should orient, not dump links

TellMe 当前 reader rewrite 只有“read more naturally”，这还不够具体。没有具体风格约束，模型很容易做成：

- 把 bullet 换成更长的 bullet
- 把 summary 换成更顺一点的 summary
- 保留原有 claim/evidence 骨架不动

这类改写很难真正提升阅读体验。

## 4. TellMe 没有把“读者问题”放进抽取链路

TellMe 的 theme page 代码里虽然有 `## Core Question`，但这是代码模板生成出来的，不是模型在抽取阶段就被要求思考的。

参考项目里，很多 prompt 会更早要求模型考虑：

- 这篇 source 的 main argument 是什么
- 为什么这个概念重要
- 这个 synthesis 页到底在回答什么问题

这会直接决定文章是否有中心。

TellMe 现在容易在页面里出现：

- 有 Summary
- 有 Claims
- 有 Relations

但不一定有一个真正能串起它们的中心问题。

## 5. TellMe 过早把 evidence 推到前台

TellMe 的 graph staging page 会很早展示：

- claim 的 source
- relation 的 source
- evidence list

这对 review 很好，但对读者不一定好。可读性更强的写法通常是：

- 正文先解释
- 证据后置
- 必要时在段内做轻量 attribution

参考项目里更常见的是“解释优先，来源跟随”，而不是“来源和结构先把页面骨架撑满”。

## 6. TellMe 的 health 体系还没把“可读性”当成一类 health finding

现在 TellMe health finding 偏这些类别：

- thin_node
- missing_node
- weak_link
- duplicate_concept
- conflict_followup

但如果目标是提升 `wiki/` 的可读性，还应该有一类 reader-facing health finding，比如：

- `weak_overview`
- `theme_without_narrative`
- `reference_too_card_like`
- `claim_dump_page`
- `missing_reading_path`

这类 finding 不一定影响图谱正确性，但会影响人类到底愿不愿意读下去。

## 对 TellMe 最有价值的改法

下面这些建议不是泛泛而谈，而是最可能直接提升最终 `wiki/` 内容可读性的 prompt 改法。

## 1. 把 compile handoff 拆成“抽取 prompt”和“发布 prompt”

现在 TellMe compile handoff 更像统一 prompt。更好的办法是分两层：

- **Graph Extraction Prompt**
  只负责 concepts / claims / relations / conflicts
- **Reader Publication Prompt**
  基于 graph candidate + existing wiki，负责写 theme/subtheme/reference/overview

这样可以保留 TellMe 现有的结构化优势，同时不让 reader-facing 页直接继承 graph candidate 的卡片感。

## 2. 给每种 reader-facing 页面单独写 prompt contract

至少要分四类：

- **overview**
  目标是定向，不是罗列
- **theme**
  目标是讲清楚一个大主题的主线、重要性、阅读路径
- **subtheme**
  目标是展开一个稳定分支，解释它和上一级 theme 的关系
- **reference**
  目标是给出精确定义和最必要上下文，不抢主题页的叙事角色

现在 TellMe 这些角色主要在 `indexes.py` 里由代码模板区分，还不够。应该在 prompt 里把每一类页面的“读者任务”写清楚。

## 3. 在 prompt 里加入“先回答什么问题，再写页面”

建议每次生成 reader-facing 页前，先让模型内部明确：

- 这一页的核心问题是什么
- 读者读完这页应该记住什么
- 哪些内容是这页必须讲的
- 哪些内容更适合放到 reference 或 evidence

参考项目里很多强页面之所以更好读，就是因为模型不是在“填字段”，而是在“回答一个页面问题”。

## 4. 把“解释优先，证据后置”写成强规则

TellMe 可以继续保留强 provenance，但页面写法应该改成：

- 正文先解释结论和结构
- claims 不要直接原样堆成主内容
- evidence 单独放到文末或折叠 section
- relation 列表只在必要时出现，不要默认成为正文主骨架

否则 reference/theme 页很容易像数据库导出的维基卡片。

## 5. 给 reader rewrite prompt 更具体的反模式

现在只说“read more naturally”太抽象了。建议明确禁止这些形态：

- summary + claim dump
- relation list 直接代替解释段落
- 每段都只是 source paraphrase
- 没有 opening paragraph 的 theme/subtheme 页
- 通篇只有 bullet，没有段落组织

同时要求这些正向特征：

- 开头一段先定向
- 先讲主线，再讲分支
- 段落之间有顺承，不是平铺
- reference 页短而准，theme 页长而有组织

## 6. 把“可读性检查”纳入 health handoff

TellMe 已经有 health loop，这是优势。最自然的下一步不是再加一个独立命令，而是把 reader-facing 可读性直接作为 health finding 类型之一。

比如新增：

- `weak_summary`
- `missing_orientation`
- `evidence_overwhelms_explanation`
- `theme_needs_reading_path`
- `reference_should_be_embedded`

这样系统就能定期发现“这页虽然结构合法，但不好读”。

## 最后给一个判断

如果只看知识抽取能力，TellMe 现在已经比大多数参考项目更强，因为它的 state、staging、publish、reconcile 边界都更清楚。

但如果只看 `wiki/` 目录最终给人读的页面，TellMe 现在的 prompt 体系还没有把“好读”当作一等目标。它更像一个很好的知识编排器，还不像一个很好的 wiki 编辑。

参考项目里最值得 TellMe 吸收的，不是某一个目录结构，而是这两个 prompt 思路：

- **先分析，再写**
- **先定义页面的阅读任务，再要求模型落文件**

只要 TellMe 把这两点补上，现有的 graph-first 架构不但不会妨碍可读性，反而会比参考项目更容易做出“既可追溯、又好读”的 `wiki/`。
