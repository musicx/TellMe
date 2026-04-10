---
title: Karpathy Feedback Loop Implementation Plan
status: planned
date: 2026-04-10
design:
  - docs/designs/2026-04-10-karpathy-llm-wiki-design-update.md
  - docs/designs/2026-04-10-knowledge-graph-mvp-redesign.md
execution_json: docs/plans/2026-04-10-karpathy-feedback-loop-plan.execution.json
mode: create
human_design_approval:
  status: approved
  approved_by: user
  user_approval_quote: "可以，更新我们的设计。并进行对实施计划的开发。"
---

# Karpathy Feedback Loop Implementation Plan

## Problem Summary

TellMe now supports graph candidates, staged graph pages, conflict review pages, and publishing staged graph nodes into `vault/`. Karpathy's LLM-wiki note adds a missing product loop: useful queries, generated outputs, and health checks should accumulate back into the knowledge base instead of remaining transient terminal/run artifacts.

This plan implements the first bounded version of that loop.

## Requirements And Design Trace

- `docs/designs/2026-04-10-karpathy-llm-wiki-design-update.md`: query/output should become fileable synthesis candidates; Obsidian should expose index/review surfaces; health/reflection should propose improvements.
- `docs/designs/2026-04-10-knowledge-graph-mvp-redesign.md`: raw remains evidence; vault is a published projection; LLM-generated updates must go through staging and source attribution.
- `AGENTS.md`: host outputs must write through TellMe-controlled paths and preserve provenance.

## Scope Boundary

In scope:

- Extend state with `outputs`, `syntheses`, and `health_findings` sections.
- Convert `query --stage` into a source-backed synthesis/output candidate path while preserving existing query artifact behavior.
- Extend `publish` to publish staged `synthesis` and `output` pages into `vault/synthesis/` and `vault/outputs/`.
- Generate Obsidian IDE index pages from state.
- Add a deterministic `lint --health-handoff` or equivalent health task generator for LLM hosts to propose graph improvements.

Out of scope:

- Automatic host CLI invocation.
- Vector database or semantic search infrastructure.
- Image/PDF asset processing implementation.
- Automatic web research.
- Automatic conflict resolution.
- Rich interactive review UI.

## Implementation Units

- [ ] Unit 1: State model for outputs, syntheses, and health findings.
- [ ] Unit 2: Query stage output becomes synthesis/output candidate.
- [ ] Unit 3: Publish supports synthesis/output pages and remains idempotent.
- [ ] Unit 4: Generate Obsidian IDE index pages from state.
- [ ] Unit 5: Health/reflection handoff task generation.
- [ ] Unit 6: README/AGENTS usage updates and full verification.

## Unit 1: State Model For Outputs, Syntheses, And Health Findings

Goal: Add manifest sections and minimal helper methods without introducing a new storage layer.

Files:

- `src/tellme/state.py`
- `tests/test_state.py` or nearby existing state/config tests

Constraints:

- Preserve backward compatibility with existing manifests.
- Keep state JSON file-based.
- Do not migrate to SQLite or vector storage.

Test scenarios:

- New manifest includes `outputs`, `syntheses`, and `health_findings`.
- Existing manifest without these sections normalizes successfully.
- Upsert/read helpers preserve status, sources, staged/published paths, and run metadata.

Verification:

- `python -m pytest tests/test_state.py tests/test_config.py -q`

## Unit 2: Query Stage Output Becomes Synthesis/Output Candidate

Goal: Make `query --stage` produce a reviewable candidate that can be filed back into the wiki.

Files:

- `src/tellme/query.py`
- `src/tellme/cli.py`
- `tests/test_query.py`
- `tests/test_cli.py`

Constraints:

- Query answers without source references must remain run artifacts only.
- Existing non-staged query behavior must remain compatible.
- Candidate pages must include frontmatter with `page_type`, `status`, `sources`, `question`, `last_host`, and `last_run_id`.

Test scenarios:

- `query --stage` creates `staging/synthesis/<slug>.md` when matched pages/sources exist.
- Query stage output records a synthesis/output state entry.
- Query stage refuses or downgrades unsourced answers to run artifacts.
- CLI prints the staged synthesis path.

Verification:

- `python -m pytest tests/test_query.py tests/test_cli.py -q`

## Unit 3: Publish Supports Synthesis/Output Pages

Goal: Extend existing publish flow beyond graph nodes while preserving current node publish behavior.

Files:

- `src/tellme/publish.py`
- `src/tellme/cli.py`
- `tests/test_publish.py`
- `tests/test_cli.py`

Constraints:

- `publish --all` can publish staged `concept`, `entity`, `synthesis`, and `output` pages.
- Published paths must map from `staging/synthesis/` to `vault/synthesis/` and from `staging/outputs/` to `vault/outputs/`.
- Publish must remain idempotent.
- Conflict pages remain review-only and are not auto-published by `--all`.

Test scenarios:

- Staged synthesis publishes to `vault/synthesis/`.
- Staged output publishes to `vault/outputs/`.
- Re-running `publish --all` does not republish already published pages.
- Conflict pages are skipped by `publish --all`.

Verification:

- `python -m pytest tests/test_publish.py tests/test_cli.py -q`

## Unit 4: Generate Obsidian IDE Index Pages

Goal: Make Obsidian usable as an IDE surface by generating navigation pages from state.

Files:

- New `src/tellme/indexes.py`
- `src/tellme/publish.py` or `src/tellme/cli.py`
- `tests/test_indexes.py`
- `tests/test_cli.py`

Constraints:

- Index pages are derived projections, not primary state.
- Index regeneration must be deterministic.
- Manual index edits should not be required for correctness.

Test scenarios:

- Generates `vault/index.md`.
- Generates `vault/indexes/concepts.md`, `entities.md`, `synthesis.md`, and `unresolved-conflicts.md`.
- Index pages link to known published pages.
- Empty indexes still produce useful placeholder sections.

Verification:

- `python -m pytest tests/test_indexes.py tests/test_cli.py -q`

## Unit 5: Health/Reflection Handoff Task Generation

Goal: Add the first LLM-assisted health check entry point without automatic web research or model invocation.

Files:

- `src/tellme/linting.py` or new `src/tellme/health.py`
- `src/tellme/cli.py`
- `tests/test_linting.py` or new `tests/test_health.py`

Constraints:

- Handoff writes only under `runs/` and expects resulting candidates under `staging/`.
- Deterministic lint remains available and unchanged.
- Health task should include graph summary, unresolved conflicts, orphan relations, thin nodes, and suggested output schema.

Test scenarios:

- CLI mode creates a host task Markdown/JSON for health reflection.
- Task includes known nodes, unresolved conflicts, and expected health finding schema.
- Result template points to `staging/health/<run-id>.json`.

Verification:

- `python -m pytest tests/test_health.py tests/test_linting.py tests/test_cli.py -q`

## Unit 6: Documentation And Full Verification

Goal: Keep user-facing docs aligned with the new feedback loop.

Files:

- `README.md`
- `AGENTS.md`
- `docs/designs/2026-04-10-karpathy-llm-wiki-design-update.md`
- `docs/plans/2026-04-10-karpathy-feedback-loop-plan.execution.json`

Constraints:

- Document current behavior separately from future goals.
- Keep Codex handoff examples accurate.
- Do not claim automatic LLM invocation unless implemented.

Verification:

- `python -m pytest tests -q`
- `python -m compileall src`
- `$env:PYTHONPATH='src'; python -m tellme --machine windows-dev lint`
- `python -m json.tool docs/plans/2026-04-10-karpathy-feedback-loop-plan.execution.json`

## Risks And Deferred Questions

- The line between `outputs` and `syntheses` may collapse after usage; keep both initially because outputs may include slides/images later.
- `lint --health-handoff` may become a separate `reflect` command if command semantics become too broad.
- Generated index overwrite policy needs care once users start editing index pages manually.

## Execution JSON

Execution graph: `docs/plans/2026-04-10-karpathy-feedback-loop-plan.execution.json`
