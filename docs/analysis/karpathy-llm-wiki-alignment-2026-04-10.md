---
title: Karpathy LLM-Wiki Alignment Notes
date: 2026-04-10
source: docs/designs/2026-04-02-twitter-from-karpathy.md
status: accepted_design_input
---

# Karpathy LLM-Wiki Alignment Notes

## Source Summary

Karpathy describes a personal LLM-maintained knowledge base workflow:

- Source material is indexed into `raw/`.
- An LLM incrementally compiles a markdown wiki with summaries, backlinks, concept articles, categories, and links.
- Obsidian is used as the IDE frontend for raw data, compiled wiki, and derived visualizations.
- Q&A is performed against the maintained wiki without immediately requiring heavy RAG.
- Answers are often rendered as markdown, slides, or images, then filed back into the wiki so explorations accumulate.
- LLM health checks find inconsistent data, impute missing data, propose interesting connections, and suggest new article candidates.
- Extra tools such as local search become CLI-accessible tools for the LLM.

## Design Implications For TellMe

Karpathy's workflow supports the current TellMe direction:

- Keep `raw/` as evidence, not as the wiki itself.
- Let LLM hosts maintain the wiki graph, while TellMe enforces state, provenance, staging, and publish boundaries.
- Prefer markdown/index/search mechanisms before adding a heavy RAG layer.
- Treat Obsidian as a knowledge work IDE, not only as a final rendered folder.

It also exposes gaps in TellMe's current design:

- Query outputs must be able to become durable knowledge, not only transient run artifacts.
- The vault should include index pages, synthesis pages, and output pages that make Obsidian usable as an IDE.
- Health checks should become LLM-assisted reflection, not only deterministic static lint.
- Source bundles should eventually support images and other local assets.
- Host CLIs should be able to use TellMe search/index tools during larger research tasks.

## Recommended Product Direction

TellMe should evolve from:

`raw -> graph candidate -> staging -> vault`

to:

`raw/assets -> graph candidate -> staging -> vault/indexes -> query outputs -> synthesis candidates -> vault`

This preserves the graph-first design while adding Karpathy's key product loop: every useful exploration can add up inside the knowledge base.
