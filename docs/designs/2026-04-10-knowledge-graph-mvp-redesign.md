---
title: TellMe Knowledge Graph MVP Redesign
status: partially_implemented
date: 2026-04-10
origin: user_feedback_current_chat
reference_summary: docs/analysis/reference-capability-summary-2026-04-10.md
karpathy_alignment: docs/designs/2026-04-10-karpathy-llm-wiki-design-update.md
owner_mode: engineering-led
---

# TellMe Knowledge Graph MVP Redesign

## Problem Statement

The current TellMe MVP proves orchestration mechanics but does not yet implement the intended LLM-wiki product. It can ingest raw files, publish source summaries, and exchange Codex handoff files, but the vault is still document-oriented.

The target product is knowledge-point oriented:

- Raw documents are source evidence.
- LLM hosts extract concepts, claims, entities, and relationships from raw documents.
- TellMe compares extracted knowledge with existing vault nodes.
- Existing knowledge points are enriched instead of duplicated.
- New knowledge points become new nodes.
- Contradictions become explicit conflict/explanation candidates.
- Obsidian displays the resulting wiki graph.

## Hard Boundaries

- The Git repo is source code, configuration, templates, and design history only.
- Actual data lives under a data root, not the repo root.
- Data root resolution order:
  - `$OBSIDIAN_VAULT_PATH` when non-empty.
  - Machine config overrides in `config/machines/*.toml`.
  - `~/.obsidian/llm_wiki` fallback.
- Data-root directories:
  - `raw/`: immutable evidence copies.
  - `staging/`: reviewable graph update candidates.
  - `state/`: manifests, graph indexes, source hashes.
  - `runs/`: audit trail and host task/result artifacts.
  - `vault/`: Obsidian-readable graph projection.
- `vault/` is not the database. It is the published projection.

## Revised MVP Goal

MVP is complete only when TellMe can run this loop:

```text
raw document
-> LLM host extraction
-> concept/claim/relation candidates
-> compare against existing vault graph
-> enrich existing nodes or stage new nodes
-> record source attribution and run evidence
-> publish reviewed knowledge graph pages
-> lint graph integrity
```

## Knowledge Model

TellMe should track these units explicitly:

| Unit | Meaning | Vault Projection |
|---|---|---|
| Source | Immutable raw evidence | Source pages are optional, not primary |
| Concept | Stable knowledge point | `vault/concepts/<slug>.md` |
| Entity | Person, org, project, product, system | `vault/entities/<slug>.md` |
| Claim | Atomic sourced statement | Embedded or separate claim pages depending on density |
| Relation | Link between nodes | Wikilinks plus state edge records |
| Conflict | Incompatible or tensioned claims | `staging/conflicts/` until resolved |
| Synthesis | Higher-level summary across nodes | `vault/synthesis/<slug>.md` after review |

## Compile Semantics

`tellme compile` should evolve from source-summary generation to graph update generation.

Compile phases:

1. Select raw sources that are registered or changed.
2. Build a host task containing:
   - source excerpts or paths
   - current relevant vault nodes
   - expected schema for extracted concepts/claims/relations
   - write boundaries
3. LLM host produces structured graph candidate JSON plus Markdown drafts.
4. TellMe validates candidate shape and source attribution.
5. TellMe stages:
   - updates to existing nodes
   - new concept/entity nodes
   - relation updates
   - conflict explanation candidates
6. Low-risk auto-publish may be added later; default for LLM graph updates is staging.

## Host Role

LLM hosts are not just text generators. In TellMe they perform analysis work:

- Extract core concepts and claims from raw documents.
- Compare extracted content against existing vault graph.
- Decide whether a knowledge point is new or enriches an existing node.
- Propose links between nodes.
- Identify apparent contradictions and propose explanations.
- Produce structured outputs TellMe can validate.

TellMe remains the control plane:

- It defines allowed paths.
- It validates source attribution.
- It records state and runs.
- It decides publish/stage behavior.
- It prevents direct raw mutation and unsafe vault overwrite.

## Reference Repo Alignment

- Adopt `llm-knowledge-base` lifecycle depth: compile, reflect, merge, lint.
- Adopt `obsidian-llm-wiki-local` runtime discipline: state, drafts, health checks, auditable CLI.
- Adopt `obsidian-wiki` graph governance: cross-linking, taxonomy, rebuild/update semantics.
- Adopt `second-brain` host-neutral usage model.
- Adopt `llm-wiki-plugin` single-command routing style.

## Karpathy LLM-Wiki Alignment

Karpathy's LLM-wiki note is now an accepted design input. It validates the graph-first direction and adds three product requirements:

- Obsidian should act as the IDE surface for raw evidence, compiled graph pages, staged review material, and generated outputs.
- Query outputs should be fileable back into the wiki as durable synthesis or output candidates.
- LLM health checks should propose missing knowledge, contradictions, weak links, and new article candidates instead of only reporting static lint failures.

The detailed update is captured in `docs/designs/2026-04-10-karpathy-llm-wiki-design-update.md`.

## Next Implementation Target

The first graph candidate protocol has now been introduced:

- `GraphCandidate` JSON schema.
- `compile --handoff` task wording updated for concept/claim/relation extraction.
- `compile --consume-result` accepts graph candidate JSON and stages concept pages.
- `state/manifest.json` gains graph sections for nodes, claims, relations, and conflicts.
- `lint` checks graph candidates for source attribution and broken node links.
- `publish --all` publishes reviewed staged concept/entity graph node pages into `vault/`.
- Graph candidate conflicts are staged as reviewable pages under `staging/conflicts/`.
- Codex handoff lists existing graph nodes, and candidate consumption marks nodes as `create_new` or `enrich_existing` by node id.

Remaining implementation work:

- Query/output filing loop: staged synthesis/output candidates and publish support.
- Generated Obsidian IDE indexes: `vault/index.md` and `vault/indexes/*.md`.
- LLM health/reflection candidate flow for gaps, duplicates, weak links, and new article candidates.
- Rich review workflow for selecting, rejecting, or editing individual staged graph updates.
- Deeper semantic matching/enrichment beyond exact node-id matches.
- Conflict resolution workflow after `staging/conflicts/` review.
- Host CLI invocation wrappers for Claude Code, Codex, and OpenCode instead of handoff files only.
- Deeper reconcile that reads existing Obsidian graph pages back into graph state.

This is the minimum path from current MVP mechanics toward the intended LLM-wiki product.
