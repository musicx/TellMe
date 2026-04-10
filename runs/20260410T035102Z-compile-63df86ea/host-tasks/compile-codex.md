# TellMe Codex Compile Task

Run id: `20260410T035102Z-compile-63df86ea`
Command: `compile`
Host: `codex`

## Goal

Create a reviewed Markdown candidate from the registered TellMe sources. Write your draft under `staging/codex/`, then write a result JSON artifact at `runs/20260410T035102Z-compile-63df86ea/artifacts/codex-result.json`.

## Allowed Read Roots

- `raw/`
- `state/`
- `vault/`

## Allowed Write Roots

- `staging/`
- `runs/`

Do not modify `raw/`.
Do not publish directly to `vault/`.

## Input Sources

- `raw/openai-harness-engineering.md`

## Required Result JSON

Use the template at `runs/20260410T035102Z-compile-63df86ea/artifacts/codex-result.template.json`.
The final result JSON must include `schema_version`, `status`, `host`, `run_id`, `output_path`, and `source_references`.
