---
title: Health Reflection Consumption Plan
status: completed
date: 2026-04-10
design: docs/designs/2026-04-10-health-reflection-consumption-design.md
execution_json: docs/plans/2026-04-10-health-reflection-consumption-plan.execution.json
mode: create
human_design_approval:
  status: approved
  approved_by: user
  user_approval_quote: "可以，把计划落盘，然后开始追踪执行"
---

# Health Reflection Consumption Plan

## Problem Summary

TellMe can already generate LLM-readable health/reflection handoffs, but it cannot yet consume those findings back into staged state. That leaves the health loop incomplete: host-generated findings do not become durable review work, do not appear in Obsidian surfaces, and do not guide the next graph action.

## Scope Boundary

In scope:

- Health result consume mode under `lint`.
- Health finding schema validation and path safety checks.
- `state.health_findings` registration with staged review paths.
- Markdown review pages under `staging/health/`.
- Suggested next-action routing metadata.
- Health-review lint checks and index generation.
- README and contract updates.

Out of scope:

- Auto-generating graph candidates from findings.
- Publishing health findings to `vault/` as knowledge pages.
- Automatic host invocation.
- Rich interactive review UI.

## Implementation Units

- [x] Unit 1: Health result consume model and CLI entry.
- [x] Unit 2: Staged health review page generation and state upsert.
- [x] Unit 3: Lint and index exposure for health findings.
- [x] Unit 4: Documentation alignment and full verification.

## Unit 1: Health Result Consume Model And CLI Entry

Goal: Create the safe consume path for host-written health result JSON under `staging/health/`.

Files:

- `src/tellme/cli.py`
- `src/tellme/health.py`
- `tests/test_health.py`
- `tests/test_cli.py`

Constraints:

- Reuse the existing `lint` command rather than adding a top-level `reflect` command.
- Only accept health result files under `staging/health/`.
- Keep deterministic `lint` and `--health-handoff` behavior unchanged.

Test scenarios:

- `tellme lint --consume-health-result <path>` registers a valid health result.
- The command rejects paths outside `staging/health/`.
- The command rejects malformed findings or missing required fields.
- The command rejects source references that are not registered sources.

Verification:

- `uv run --with pytest python -m pytest tests/test_health.py tests/test_cli.py -q`

## Unit 2: Staged Health Review Page Generation And State Upsert

Goal: Turn consumed findings into durable staged review work.

Files:

- `src/tellme/health.py`
- `src/tellme/state.py`
- `tests/test_health.py`

Constraints:

- Findings remain `staged`; they do not publish to `vault/`.
- Each finding must get one Markdown review page under `staging/health/`.
- Suggested next actions must be deterministic and type-driven.

Test scenarios:

- Each finding creates a review page with expected frontmatter and body sections.
- `state.health_findings` stores `status`, `sources`, `affected_ids`, `confidence`, `staged_path`, `last_host`, and `last_run_id`.
- Unknown finding types route to `manual_review`.

Verification:

- `uv run --with pytest python -m pytest tests/test_health.py -q`

## Unit 3: Lint And Index Exposure For Health Findings

Goal: Make staged health findings visible and reviewable through existing deterministic surfaces.

Files:

- `src/tellme/linting.py`
- `src/tellme/indexes.py`
- `tests/test_linting.py`
- `tests/test_indexes.py`

Constraints:

- Lint should report malformed or dangling staged health findings without blocking staging itself.
- Indexes remain projections from state; they are not a primary store.
- Root Obsidian index should link to the health review queue.

Test scenarios:

- Lint reports missing `affected_ids` targets.
- Lint reports tracked health findings whose staged pages are missing.
- `generate_vault_indexes()` creates `vault/indexes/health-review.md`.
- Root index links to the health review queue and the queue links to staged health pages.

Verification:

- `uv run --with pytest python -m pytest tests/test_linting.py tests/test_indexes.py -q`

## Unit 4: Documentation Alignment And Full Verification

Goal: Keep operator docs aligned with the new consume and review loop.

Files:

- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/plans/2026-04-10-health-reflection-consumption-plan.execution.json`

Constraints:

- Document current behavior, not aspirational automation.
- Keep examples aligned with the actual CLI.
- `CLAUDE.md` should stay in sync with `AGENTS.md` in the next commit as requested.

Verification:

- `uv run python -m tellme --help`
- `uv run --with pytest python -m pytest tests -q`

## Risks And Deferred Questions

- We are introducing a second staged artifact family under `staging/health/`; naming and page shape should stay simple to avoid accidental parallel workflow sprawl.
- Automatic conversion from findings to graph candidates is intentionally deferred so review remains explicit.
