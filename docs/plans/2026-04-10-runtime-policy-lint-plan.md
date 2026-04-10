---
title: Runtime Policy And Lint Plan
status: completed
date: 2026-04-10
origin: docs/verification/2026-04-10-design-implementation-gap.md
design: docs/designs/2026-04-10-runtime-policy-lint-design.md
execution_json: docs/plans/2026-04-10-runtime-policy-lint-plan.execution.json
mode: create
---

# Runtime Policy And Lint Plan

## Problem Summary

TellMe has usable MVP commands, but config and policy files are still mostly passive. Static lint also misses important state-level safety checks. This plan implements the next non-LLM foundation slice: host/policy runtime loading plus stronger deterministic lint.

## Scope Boundary

In scope:

- Host config dataclass and runtime loading.
- Policy config loading from `config/policies/*.toml`.
- Default host and policy files created by `init`.
- Compile publish/stage behavior controlled by `publish.source_summary_direct_publish`.
- Lint checks for page hash drift and running runs.

Out of scope:

- Host CLI invocation.
- Provider API integration.
- Semantic lint or vector indexes.
- Reconcile merge candidates.

## Implementation Units

- [x] Unit 1: Runtime host and policy config loading.
- [x] Unit 2: Compile publish policy behavior.
- [x] Unit 3: Static lint drift and running-run checks.
- [x] Unit 4: README usage update and verification.

## Verification

- `python -m pytest tests/test_config.py tests/test_compile.py tests/test_linting.py tests/test_cli.py -q`
- `python -m pytest tests -q`
- CLI smoke: `init -> ingest -> compile -> lint`
