---
title: TellMe Orchestrator Foundation Plan
type: feat
status: completed
date: 2026-04-10
origin: docs/tellme-design.md
design: docs/designs/2026-04-10-tellme-optimization-design.md
design_approval: docs/approvals/2026-04-10-tellme-optimization-design-approval.md
execution_json: docs/plans/2026-04-10-tellme-orchestrator-foundation-plan.execution.json
mode: create
deepened: none
---

# TellMe Orchestrator Foundation Plan

## Overview

This plan turns TellMe from a CLI and persistence skeleton into a usable local orchestration foundation. The work keeps the first implementation file-backed and host-agnostic: commands resolve project/config, mutating workflows create auditable run records, sources ingest into `raw/`, state evolves with schema versions, static lint/reconcile become useful without LLMs, and host task/result JSON artifacts establish the first cross-host protocol.

## Problem Frame

TellMe already has a committed skeleton with six CLI commands, `ProjectState`, and `RunStore`. The next implementation phase must add enough behavior that future LLM-assisted compile/query work has reliable boundaries instead of each command inventing its own config, state, run, and host-handoff semantics.

## Requirements Trace

- R1. TellMe must run on PC and MacBook through configurable paths.
- R2. TellMe must support Claude Code, Codex, and OpenCode as host entry points.
- R3. Obsidian must remain the display layer, not the system database.
- R4. The MVP command surface is `init`, `ingest`, `compile`, `query`, `lint`, and `reconcile`.
- R5. Direct host edits to `vault/` are allowed but must be recoverable through `reconcile`.
- R6. Low-risk changes may publish directly; higher-risk changes must stage first.
- R7. System state and operation history must be explicit and reviewable.

## Design Trace

- D1. Every command follows the common lifecycle: resolve project, load config, create run, execute workflow, persist status.
- D2. External file ingest copies sources into `raw/` by default.
- D3. Host-assisted work exchanges versioned JSON task/result artifacts under `runs/<run-id>/`.
- D4. Query and most LLM-generated content stage by default; only low-risk source summaries may auto-publish after attribution and lint checks.
- D5. Reconcile preserves human edits and stages conflict candidates instead of silently overwriting.
- D6. Manifest remains JSON-backed in the next phase, with a schema version and atomic writes.

## Approval Trace

- Human Design Approval: `docs/approvals/2026-04-10-tellme-optimization-design-approval.md`
- Approval Constraints To Preserve:
  - `raw/` remains immutable after ingest registration.
  - `vault/` remains display/published surface, not the full system state.
  - Host output is input to TellMe, not final canonical state by itself.
  - Planning must include a first-iteration concurrency stance and schema versioning for host artifacts.

## Scope Boundaries

- This plan does not implement real LLM calls.
- This plan does not implement direct provider SDK integrations.
- This plan does not implement vector search, qmd integration, or semantic indexing.
- This plan does not implement an Obsidian plugin.
- This plan does not implement full markdown synthesis for concept/entity/synthesis pages.
- This plan does not introduce SQLite; JSON state remains the implementation target.

## Relevant Context

### Existing Patterns

- `src/tellme/cli.py`: argparse-based command surface.
- `src/tellme/project.py`: idempotent project directory creation.
- `src/tellme/state.py`: JSON-backed manifest with dataclass records.
- `src/tellme/runs.py`: one run directory with `run.json`.
- `tests/test_cli.py`: subprocess CLI tests with `PYTHONPATH=src`.
- `tests/test_state_runs.py`: persistence tests for state and run models.

### Existing Constraints

- New behavior should be test-first.
- Project-relative POSIX paths should be stored in state.
- User config and existing files must not be overwritten silently.
- `raw/` must not be mutated after source registration except for initial copy into raw.

### Prior Learnings

- `obsidian-llm-wiki-local` supports using a Python CLI plus state persistence as the reliable core pattern.
- `obsidian-wiki` and `second-brain` show that host compatibility needs shared instructions/protocols rather than separate semantics per host.
- `llm-knowledge-base` shows lightweight index/search can be layered later; first build reliable lifecycle state.

### Research Notes

- No external research needed for this plan; local reference repo analysis is already captured in `docs/analysis/`.

## Key Technical Decisions

- Add a resolver/config layer before expanding workflow commands: Commands should not each invent project-root and machine-path behavior.
- Keep writes JSON-backed but atomic: This preserves transparency while reducing corruption risk from interrupted writes.
- Use a simple project lock for mutating commands in this implementation phase: This resolves the design challenge's concurrency finding without overbuilding a daemon.
- Add `schema_version` to manifest, run records, host tasks, and host results: This resolves the design challenge's compatibility finding.
- Implement static lint before LLM lint: This provides immediate value and supports safe publish/reconcile checks.
- Implement host packet schema before real compile/query synthesis: This lets future host work plug into audited runs.

## Open Questions

### Resolved During Planning

- Concurrency stance: First implementation uses a lightweight lock for mutating commands; parallel mutation is out of scope.
- Host artifact versioning: All task/result artifacts include `schema_version`.
- External source behavior: First implementation copies external file sources into `raw/`.

### Deferred To Execution

- Exact wording of user-facing messages: Execution can refine wording as long as error conditions and recovery guidance remain explicit.
- Exact internal helper names: Execution can choose names inside the files listed in each unit.
- Whether static lint supports every markdown edge case: First implementation only needs documented basic wikilink/frontmatter/hash checks.

## Implementation Units

- [x] **Unit 1: Project Resolution And Config Loading**

**Goal:** Add a deterministic project runtime boundary so commands can find project root, load TOML config, and resolve machine paths.

**Requirements:** R1, R3, R4, R7

**Dependencies:** None

**Files:**
- Create: `src/tellme/config.py`
- Create: `src/tellme/resolver.py`
- Modify: `src/tellme/cli.py`
- Modify: `src/tellme/project.py`
- Test: `tests/test_config.py`
- Test: `tests/test_cli.py`

**Constraints:**
- Do not require global user config.
- Do not guess between multiple possible project roots.
- Store and return project-relative paths where state is involved.

**Approach:**
- Detect project root by explicit `--project` or upward search for `config/project.toml`.
- Load `config/project.toml`, optional machine config, host config, and policy configs.
- Fail with clear errors when required config is missing.

**Patterns To Follow:**
- Existing `init_project()` idempotency.
- Existing argparse command structure.

**Execution Note:** test-first

**Test Scenarios:**
- Happy path: command run under a TellMe project resolves the root and config.
- Edge case: explicit `--project` resolves a project from outside the tree.
- Failure path: command outside a project exits non-zero with recovery guidance.
- Integration: `tellme init` creates config that the resolver can immediately load.

**Verification:**
- `python -m pytest tests/test_config.py tests/test_cli.py -q`

**Done When:**
- CLI commands can consistently resolve project runtime context without hard-coded cwd assumptions.

- [x] **Unit 2: Run Lifecycle, Audit Directory, And Locking**

**Goal:** Expand run records into the approved run-directory shape and ensure mutating commands have a first-iteration concurrency guard.

**Requirements:** R4, R7

**Dependencies:** Unit 1

**Files:**
- Modify: `src/tellme/runs.py`
- Create: `src/tellme/locks.py`
- Create: `src/tellme/workflow.py`
- Modify: `src/tellme/cli.py`
- Test: `tests/test_runs.py`
- Test: `tests/test_workflow.py`

**Constraints:**
- Run record must be written before command mutation.
- Locking must be local and file-backed.
- Stale/running runs must remain inspectable, not deleted.

**Approach:**
- Add `partial` and `cancelled` run statuses.
- Create `input.json`, `diagnostics.md`, `host-tasks/`, and `artifacts/` directories for each run.
- Add a simple lock for mutating commands with clear failure behavior when held.

**Patterns To Follow:**
- Existing `RunStore.start()` and `RunStore.complete()` pattern.
- JSON records with dataclass serialization.

**Execution Note:** test-first

**Test Scenarios:**
- Happy path: a workflow creates `run.json`, `input.json`, `host-tasks/`, and `artifacts/`.
- Edge case: completing a run as `partial` preserves diagnostics and outputs.
- Failure path: second mutating workflow fails while lock is held.
- Integration: CLI mutating command creates a run even when workflow returns an error.

**Verification:**
- `python -m pytest tests/test_runs.py tests/test_workflow.py -q`

**Done When:**
- Run artifacts match the design shape and concurrent mutation has an explicit first-version behavior.

- [x] **Unit 3: Manifest Schema Evolution And Atomic State Writes**

**Goal:** Evolve the JSON manifest to support versioned sources, pages, links, indexes, and atomic persistence.

**Requirements:** R3, R5, R7

**Dependencies:** Unit 1, Unit 2

**Files:**
- Modify: `src/tellme/state.py`
- Create: `src/tellme/files.py`
- Test: `tests/test_state_runs.py`
- Test: `tests/test_state_schema.py`

**Constraints:**
- Preserve compatibility with the existing minimal manifest where practical.
- All state paths stored in manifest should be project-relative POSIX paths.
- Do not introduce SQLite in this phase.

**Approach:**
- Add `schema_version`.
- Expand `SourceRecord` with source type, raw path, original path, registration run id, and status timestamps as needed.
- Expand `PageRecord` with staged/published distinction and frontmatter-relevant metadata.
- Add link and index sections as first-class manifest keys.
- Write manifest atomically using temp file then replace.

**Patterns To Follow:**
- Existing `ProjectState.create/load/upsert_*` shape.
- Existing tests comparing reloaded dataclasses.

**Execution Note:** test-first

**Test Scenarios:**
- Happy path: new manifest includes versioned `sources`, `pages`, `links`, and `indexes`.
- Edge case: loading an older minimal manifest succeeds or produces a controlled migration.
- Failure path: invalid manifest schema fails with a specific error.
- Integration: `init` creates a manifest compatible with state schema tests.

**Verification:**
- `python -m pytest tests/test_state_runs.py tests/test_state_schema.py -q`

**Done When:**
- State persistence is versioned, inspectable, and ready for ingest/lint/reconcile workflows.

- [x] **Unit 4: Ingest Workflow V1**

**Goal:** Implement source registration for file inputs, copying external files into `raw/`, recording state, and producing run audit output.

**Requirements:** R1, R3, R4, R7

**Dependencies:** Unit 1, Unit 2, Unit 3

**Files:**
- Create: `src/tellme/ingest.py`
- Modify: `src/tellme/cli.py`
- Modify: `src/tellme/state.py`
- Test: `tests/test_ingest.py`
- Test: `tests/test_cli.py`

**Constraints:**
- `ingest` does not perform deep synthesis.
- External file inputs copy into `raw/` by default.
- Existing raw files are not overwritten silently.
- URL ingest is out of scope unless represented as a small metadata source file.

**Approach:**
- Add `tellme ingest <path>`.
- Detect whether source is already under `raw/`.
- Copy external files to a collision-safe raw path.
- Hash content, upsert source record, complete run.

**Patterns To Follow:**
- File-backed state and run stores.
- Existing CLI subprocess test style.

**Execution Note:** test-first

**Test Scenarios:**
- Happy path: external markdown file is copied into `raw/` and registered.
- Edge case: same file ingested twice does not overwrite raw content silently.
- Failure path: missing source path exits non-zero and records failed run when project context exists.
- Integration: `tellme ingest` from outside project works with `--project`.

**Verification:**
- `python -m pytest tests/test_ingest.py tests/test_cli.py -q`

**Done When:**
- File source ingest is usable and auditable without LLM integration.

- [x] **Unit 5: Static Lint And Reconcile Foundation**

**Goal:** Add non-LLM health checks and vault drift detection that preserve human edits.

**Requirements:** R3, R4, R5, R6, R7

**Dependencies:** Unit 1, Unit 2, Unit 3

**Files:**
- Create: `src/tellme/markdown.py`
- Create: `src/tellme/linting.py`
- Create: `src/tellme/reconcile.py`
- Modify: `src/tellme/cli.py`
- Modify: `src/tellme/state.py`
- Test: `tests/test_linting.py`
- Test: `tests/test_reconcile.py`
- Test: `tests/test_cli.py`

**Constraints:**
- No LLM-dependent contradiction detection in this phase.
- Reconcile must not overwrite published human edits.
- Conflict output must go to `staging/` or run artifacts, not directly overwrite `vault/`.

**Approach:**
- Parse markdown frontmatter minimally.
- Extract Obsidian-style `[[wikilinks]]`.
- Check missing frontmatter, broken links, orphan-like pages, missing source metadata, and hash drift.
- Reconcile benign hash drift into state and stage merge candidates for conflicts.

**Patterns To Follow:**
- Static checks first, LLM enhancement later.
- Project-relative POSIX paths in state.

**Execution Note:** test-first

**Test Scenarios:**
- Happy path: valid vault page passes static lint.
- Edge case: page with missing frontmatter reports a lint issue.
- Failure path: broken wikilink reports issue and command exits according to severity.
- Integration: modified published page is detected by reconcile and state is updated or conflict staged without overwrite.

**Verification:**
- `python -m pytest tests/test_linting.py tests/test_reconcile.py tests/test_cli.py -q`

**Done When:**
- `tellme lint` and `tellme reconcile` provide useful local safety checks without model calls.

- [x] **Unit 6: Host Task And Result Artifact Protocol**

**Goal:** Define the first stable JSON protocol for Claude Code, Codex, and OpenCode task handoffs.

**Requirements:** R2, R4, R6, R7

**Dependencies:** Unit 1, Unit 2, Unit 3

**Files:**
- Create: `src/tellme/hosts.py`
- Modify: `src/tellme/runs.py`
- Create: `templates/host-task.schema.json`
- Create: `templates/host-result.schema.json`
- Test: `tests/test_hosts.py`
- Test: `tests/test_runs.py`

**Constraints:**
- Include `schema_version` in every task and result artifact.
- Do not call host CLIs in this phase.
- Task packets must declare allowed read/write roots.
- Host results are not canonical until TellMe consumes them.

**Approach:**
- Add dataclasses for host task and host result artifacts.
- Write task packets under `runs/<run-id>/host-tasks/`.
- Read result artifacts from `runs/<run-id>/artifacts/`.
- Validate required fields before consuming a result.

**Patterns To Follow:**
- Existing JSON dataclass serialization.
- Run-directory design from Unit 2.

**Execution Note:** test-first

**Test Scenarios:**
- Happy path: host task packet is written with schema version and allowed roots.
- Edge case: unknown host name fails validation.
- Failure path: result artifact missing source references is rejected.
- Integration: compile/query skeleton can create a host task without invoking a host.

**Verification:**
- `python -m pytest tests/test_hosts.py tests/test_runs.py -q`

**Done When:**
- The host exchange protocol is explicit, versioned, and usable by later compile/query work.

## Review Watchpoints

- Product concern reviewers should check whether the operator can understand when content is merely staged versus published.
- Engineering reviewers should check whether the plan keeps state, runs, config, and host protocol boundaries separate.
- Operations reviewers should check failure persistence, lock behavior, and recovery from interrupted runs.

## Execution JSON

- Path: `docs/plans/2026-04-10-tellme-orchestrator-foundation-plan.execution.json`
- Status: created
- Must match the implementation units, dependencies, boundaries, verification, and acceptance criteria in this Markdown plan.

## Risks

- Risk: Lightweight locking may be too simple for future multi-host concurrency.
  - Mitigation: Make concurrent mutation explicitly unsupported beyond one local lock in this phase.
- Risk: JSON manifest may become cumbersome.
  - Mitigation: Keep schema versioned so SQLite migration remains possible later.
- Risk: Host task protocol may need changes after real Claude/Codex/OpenCode use.
  - Mitigation: Version task/result artifacts from the first implementation.

## Plan Critique Result

- Design consistency review: pass
- Engineering feasibility review: pass
- Scope and risk review: pass
- Readiness decision: ready_for_package_challenge

## Plan Quality Check

- Requirements covered: yes
- Design decisions preserved: yes
- Exact file paths named: yes
- Execution JSON exists and matches plan: yes
- Feature-bearing units have test scenarios: yes
- Execution boundaries are reviewable: yes
- Research shaped the plan where needed: yes
- Deferred questions are truly execution-owned: yes
- Critique stack cleared when needed: yes

## Recommended Next Step

- `cmon:challenge(mode=package)`
