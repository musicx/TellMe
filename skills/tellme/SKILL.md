---
name: tellme
description: Use when the user asks you to ingest sources, compile a knowledge graph, review staged pages, query the wiki, publish content, or reconcile drift in a TellMe project. TellMe is a local LLM-wiki orchestrator where you (the host) do the language work and the `tellme` CLI is the source of truth for state. Always drive work through `tellme` subcommands rather than editing state/ or wiki/ directly.
---

# tellme

You are working inside a TellMe project. TellMe splits a knowledge base into four layers:

- `raw/` — original source files (never edit).
- `staging/` — candidates waiting for review (compile output, query synthesis, health findings, conflicts).
- `wiki/` — published, reader-facing pages displayed in Obsidian.
- `state/` and `runs/` — manifest and run metadata. Driven by the CLI.

Your job is to run `tellme` commands, read the task markdown the CLI generates, produce the LLM-side artifacts the CLI asks for, and hand control back to the CLI. Do not edit `state/`, `runs/`, `wiki/`, or `raw/` by hand, and do not invent your own staging paths — let the CLI tell you where things go.

## Quick orientation before acting

Before running any command, confirm:

1. You know the project root (contains `config/project.toml`). If the user did not say, look for it with `ls` or ask.
2. You pass the host flag: `tellme --project <path> --host claude-code <command>`. Every run must be attributed to a host.
3. You know which layer the user's request touches. The decision tree below is the rule.

## Decision tree

**"Add this file / URL / note to the knowledge base."**
→ `tellme --project <path> ingest <source>`. Registers the source under `raw/` and marks it for compile.

**"Process the new sources" / "update the graph" / "extract concepts from the new stuff."**
→ `tellme --project <path> --host claude-code compile --handoff`
The CLI writes `runs/<run-id>/host-tasks/compile-claude-code.md` and a result template JSON. Read the task markdown, do the extraction work following its rules (knowledge filter, node IDs, confidence labels, Chinese content), write a graph candidate JSON to `staging/graph/candidates/<run-id>.json`, and write the result JSON to the path the template tells you.
Then: `tellme --project <path> --host claude-code compile --consume-result <result.json>`
This validates the candidate and stages nodes/claims/relations/conflicts into `staging/`.

Never run `tellme compile` without `--handoff` or `--consume-result` — that path has been removed.

**"What's waiting for review?" / "Show me staged work."**
→ Read `staging/` directly (it's in the Obsidian vault). Also check `wiki/indexes/health-review.md` and `wiki/indexes/unresolved-conflicts.md`. Staged items that survive here mean: pending review, conflict, or uncertain.

**"Publish the staged work." / "Push reviewed pages to wiki."**
→ `tellme --project <path> --host claude-code publish --all`
Or for a specific staged path: `publish --staged-path staging/concepts/foo.md`.
Nodes flagged `update_action: uncertain` and conflict pages are skipped automatically. After a successful publish, the staged file and its PageRecord are deleted — only surviving staging entries carry semantic meaning.

**"Answer a question from the wiki." / "What does the wiki say about X?"**
→ `tellme --project <path> --host claude-code query "<question>"` — runs a deterministic match against published pages. Add `--stage` to drop a synthesis candidate into `staging/synthesis/` for later publish.

**"Check the wiki for drift / orphan pages / broken links."**
→ `tellme --project <path> lint`
To produce an LLM-driven health report: add `--health-handoff` and follow the same task-markdown + consume pattern as compile. Resolve a finding with `lint --resolve-health-finding <id>`.

**"I edited a wiki page by hand — make tellme aware."**
→ `tellme --project <path> reconcile`. Absorbs manual edits under `wiki/` back into state and retires stale automatic candidates.

**"Rewrite the reader pages to flow better."**
→ `tellme --project <path> --host claude-code publish --reader-rewrite-handoff`, do the rewrite work, then `publish --consume-reader-rewrite <result.json>` and finally `publish --all`.

## Handoff workflow (compile / reader-rewrite / health)

All three follow the same shape and must be executed in order:

1. Run the `--handoff` command. The CLI prints two paths: `task_markdown_path` and `result_template_path`.
2. Read the task markdown **in full** before writing anything. It contains the current prompt rules (node schema, filtering policy, confidence labels, language requirements). Those rules can evolve — never rely on the copy in this skill, always read the fresh one.
3. Read the result template to see the expected JSON shape.
4. Do the work. Write the candidate artifact to `staging/...` (path specified by the task) and the result JSON to the location named by the template.
5. Run the corresponding `--consume-result` command and pass the result JSON path.

If the consume step errors, the candidate is invalid. Read the error, fix the JSON, and consume again — do not hand-edit `state/` to work around a validation failure.

## Graph candidate rules you must follow

When producing a compile candidate:

- **Knowledge filter is the point, not exhaustive extraction.** Read the task markdown's "Existing Graph Nodes" list first. Prefer `enrich_existing` (reuse the existing `id` verbatim) to `create_new`. Use `update_action_hint: "uncertain"` when you can't tell — do not guess.
- **Deterministic IDs.** New nodes: `id` = `{kind}:{slug(title)}` with `kind ∈ {concept, entity}`. Slug lowercases ASCII, collapses whitespace and ASCII punctuation to `-`, and preserves CJK characters. Same concept must always produce the same id.
- **Confidence on edges.** Every claim and relation should carry `confidence ∈ {extracted, inferred, ambiguous}`; `ambiguous` is valuable, do not drop it. Optional `confidence_score` is a float 0.0–1.0.
- **Content depth.** Each node needs a short `summary` (1–2 sentence Chinese definition for index use) **plus** multi-paragraph Chinese `content` and 3–7 `key_points`. This is what makes theme and subtheme pages readable — without it, indexes collapse back into node-title lists.
- **Language.** `summary`, `content`, `key_points`, and claim `text` are Chinese. Structural fields (ids, kinds, confidence labels, update_action_hint) stay English.

## What not to do

- Do not write to `raw/` or `wiki/` directly during a compile or consume step. The CLI owns those writes.
- Do not skip `--host`. Runs without host attribution are rejected.
- Do not hand-edit `state/state.json` to "fix" something. Use the CLI subcommand that owns that data.
- Do not assume a staged file is authoritative after publish — it's gone. Read from `wiki/` for published content.
- Do not invent new update_action values, new confidence labels, or new node kinds. The CLI validates and will reject them.

## When the user pushes back on the process

If the user says "just edit the wiki page directly," do it only in Obsidian-owned files under `wiki/`, then remind them they'll need to run `tellme reconcile` afterwards so state stays consistent. Never hand-edit staged pages or state records as a shortcut.
