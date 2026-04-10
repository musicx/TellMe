---
title: Codex Collaboration Plan
status: completed
date: 2026-04-10
design: docs/designs/2026-04-10-codex-collaboration-design.md
execution_json: docs/plans/2026-04-10-codex-collaboration-plan.execution.json
mode: create
---

# Codex Collaboration Plan

## Problem Summary

TellMe needs an MVP-complete Codex collaboration loop. The current host JSON packet is not enough because Codex needs a readable task and TellMe needs a safe result intake path.

## Scope Boundary

In scope:

- Human-readable Codex task Markdown.
- Codex result template.
- `compile --handoff`.
- `compile --consume-result`.
- State registration of staged Codex output.

Out of scope:

- Codex CLI invocation.
- Auto-publish.
- Merge conflict resolution.
- Non-Codex host-specific workflow automation.

## Implementation Units

- [x] Unit 1: Codex task Markdown and result template generation.
- [x] Unit 2: Compile handoff CLI mode.
- [x] Unit 3: Compile consume-result CLI mode and staged PageRecord registration.
- [x] Unit 4: README usage and full verification.

## Verification

- `python -m pytest tests/test_codex_collaboration.py tests/test_cli.py -q`
- `python -m pytest tests -q`
- CLI smoke: `init -> ingest -> compile --handoff -> write staged result -> compile --consume-result`
