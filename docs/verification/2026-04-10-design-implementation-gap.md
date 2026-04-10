# Design / Implementation Gap Check

Date: 2026-04-10

## Current Result

TellMe now has V1 behavior for all six approved MVP commands:

- `init`: initializes project layout, config, machine mapping, state, and runs.
- `ingest`: copies external files into `raw/`, hashes them, and registers source state.
- `compile`: publishes deterministic source-summary pages into `vault/` with attribution and run metadata.
- `query`: reads published vault pages first and writes a query answer artifact under `runs/`; optional writeback goes to `staging/queries/`.
- `lint`: runs static vault checks for frontmatter, source metadata, and broken wikilinks.
- `reconcile`: detects changed known vault pages and updates page hash state without overwriting human edits.

## Remaining Gaps Against Full Design

- Real LLM synthesis is not implemented. `compile` does not yet generate concept, entity, or synthesis pages.
- Direct model-provider APIs are not implemented by design; host task/result JSON is the current integration boundary.
- Host CLI automation is not implemented. `--host` records host identity and writes host task packets, but TellMe does not invoke Claude Code, Codex, or OpenCode.
- Config loading is still shallow. Project and machine config load, but `config/hosts/*.toml` and `config/policies/*.toml` are not yet merged into runtime behavior.
- Publish policy is minimal. Low-risk source summaries publish directly; high-risk staging rules are not yet fully modeled.
- Static lint is useful but incomplete. Orphan pages, index drift, stale page hashes, and running-run leftovers still need explicit checks.
- Reconcile is conservative. It absorbs known page hash drift, but does not yet stage merge candidates for real conflicts.
- Manifest page metadata is still thinner than the full design. Frontmatter now includes created/updated metadata for generated pages, but manifest records do not yet carry all future fields such as risk, confidence, and human-edit markers.

## Next Engineering Priority

The next highest-value implementation slice is config/policy/host loading plus stronger static lint. That will make future LLM-assisted compile/query work safer without prematurely adding model-provider calls.
