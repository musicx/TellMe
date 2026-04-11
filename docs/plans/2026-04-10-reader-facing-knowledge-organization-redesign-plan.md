---
title: Reader-Facing Knowledge Organization Redesign Plan
status: completed
date: 2026-04-10
design: docs/designs/2026-04-10-reader-facing-knowledge-organization-redesign.md
execution_json: docs/plans/2026-04-10-reader-facing-knowledge-organization-redesign-plan.execution.json
mode: create
human_design_approval:
  status: approved
  approved_by: user
  user_approval_quote: "可以继续"
---

# Reader-Facing Knowledge Organization Redesign Plan

## Problem Summary

TellMe's current publish layer maps graph nodes too directly into concept/entity pages. This preserves internal structure but produces a vault that feels like a collection of extracted cards instead of an organized knowledge product. The next implementation slice introduces a reader-facing publication model centered on `overview`, `theme`, `subtheme`, and promoted `reference` pages.

## Scope Boundary

In scope:

- Introduce a reader-facing publication model with `overview`, `themes`, `subthemes`, and `references`.
- Allow staged graph nodes to carry minimal organization metadata needed for publication.
- Generate chapter-like theme and subtheme pages from published graph state.
- Move promoted reader-facing standalone nodes into `vault/references/`.
- Keep maintenance-oriented indexes available under `vault/indexes/`.
- Update tests and docs for the new publish shape.

Out of scope:

- Full automatic migration of all historical vault content.
- Rich LLM-generated theme prose beyond bounded deterministic composition.
- Theme splitting heuristics driven by health/reflection.
- Backlink/redirect preservation from old concept/entity URLs.
- Full deprecation of maintenance indexes.

## Implementation Units

- [x] Unit 1: Organization metadata for staged graph nodes.
- [x] Unit 2: Reader-facing publish model for overview, themes, subthemes, and references.
- [x] Unit 3: Reader-facing indexes and maintenance-surface updates.
- [x] Unit 4: Documentation alignment, example refresh, and verification.

## Unit 1: Organization Metadata For Staged Graph Nodes

Goal: Allow staged graph nodes to express how they should appear in the reader-facing vault.

Files:

- `src/tellme/graph.py`
- `src/tellme/state.py`
- `tests/test_graph.py`
- `tests/test_codex_collaboration.py`

Constraints:

- Keep current graph candidate schema backward-compatible.
- New organization metadata must remain optional for old candidates.
- Nodes without explicit organization metadata should still publish safely through a deterministic fallback.

Test scenarios:

- Graph candidates may include `theme`, `subtheme`, and `reader_role`.
- Staged node state preserves these fields.
- Invalid `reader_role` values are rejected.

Verification:

- `uv run --with pytest python -m pytest tests/test_graph.py tests/test_codex_collaboration.py -q`

## Unit 2: Reader-Facing Publish Model

Goal: Publish graph state into a readable vault structure rather than direct node-card output only.

Files:

- `src/tellme/publish.py`
- `src/tellme/indexes.py`
- `tests/test_publish.py`
- `tests/test_indexes.py`

Constraints:

- `overview`, `theme`, and `subtheme` pages are derived reader-facing pages.
- Promoted reference pages publish under `vault/references/`.
- Non-promoted nodes should not automatically become standalone reader-facing pages.
- Existing synthesis/output publish behavior should remain intact.

Test scenarios:

- Publishing grouped nodes creates `vault/themes/<slug>.md`.
- Publishing grouped nodes creates `vault/subthemes/<slug>.md` when subthemes are present.
- Promoted nodes publish to `vault/references/<slug>.md`.
- The reader-facing root page becomes an overview rather than a pure maintenance index.

Verification:

- `uv run --with pytest python -m pytest tests/test_publish.py tests/test_indexes.py -q`

## Unit 3: Reader-Facing Indexes And Maintenance Surfaces

Goal: Keep the new reader-facing structure usable while preserving operational visibility.

Files:

- `src/tellme/indexes.py`
- `tests/test_indexes.py`
- `README.md`

Constraints:

- Reader-facing navigation should prioritize `themes`, `subthemes`, and `references`.
- Maintenance indexes for concepts/entities/health/conflicts may remain, but as secondary surfaces.
- Root navigation should tell the reader where to start, not just list data buckets.

Test scenarios:

- `vault/index.md` points readers toward themes and overview-style navigation.
- `vault/indexes/` retains maintenance surfaces without acting as the primary information architecture.
- Empty-state output remains useful and understandable.

Verification:

- `uv run --with pytest python -m pytest tests/test_indexes.py -q`

## Unit 4: Documentation Alignment, Example Refresh, And Verification

Goal: Make the new publication shape understandable to operators and keep the example aligned.

Files:

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- example files under `~/Documents/obsidian_vault/llm_wiki/` as needed
- `docs/plans/2026-04-10-reader-facing-knowledge-organization-redesign-plan.execution.json`

Constraints:

- Document only behaviors that are actually implemented.
- Keep the existing example usable after the new publish model lands.
- Call out that this is a first slice toward strong migration, not the complete migration itself.

Verification:

- `uv run python -m tellme --help`
- `uv run --with pytest python -m pytest tests -q`
- Example vault refresh and `tellme lint`

## Risks And Deferred Questions

- Theme/subtheme generation may feel too skeletal if deterministic composition is too shallow; that is acceptable for this first slice as long as structure and navigation improve materially.
- Backward compatibility with existing `vault/concepts/` and `vault/entities/` URLs is intentionally deferred.
