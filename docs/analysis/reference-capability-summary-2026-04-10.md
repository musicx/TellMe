# Reference Capability Summary For TellMe Redesign

Date: 2026-04-10

## Why This Refresh Exists

The first TellMe implementation proved local orchestration mechanics, but it drifted toward a source-summary pipeline. The intended product is stronger: raw documents are evidence, while the Obsidian vault should present a knowledge-point wiki graph maintained by LLM hosts.

This refresh re-reads the local reference repos and existing analysis to identify the capabilities TellMe must absorb next.

## Capability Matrix

| Capability | `llm-knowledge-base` | `obsidian-llm-wiki-local` | `obsidian-wiki` | `second-brain` | `llm-wiki-plugin` | TellMe Implication |
|---|---|---|---|---|---|---|
| Source ingest | Strong skill workflow | Python pipeline | Skill-based | Skill-based | Plugin command | Keep `ingest`, but raw is evidence only |
| Knowledge compile | Strong `kb-compile` | LLM compile pipeline | `wiki-ingest` / rebuild | ingest skill | `wiki compile` | Compile must produce knowledge nodes, not document mirrors |
| Reflection / discovery | Strong `kb-reflect` | Limited | taxonomy / rebuild | limited | limited | Add graph reflection for missing concepts and synthesis candidates |
| Merge / update existing knowledge | `kb-merge` / `kb-merge-vault` | approve/reject drafts | update / cross-link skills | query/lint only | remove/update route | TellMe needs node-level enrichment and conflict staging |
| Cross-linking | Search/index driven | indexer / vault utilities | explicit `cross-linker` | schema guidance | wiki commands | Links must be first-class graph edges |
| Taxonomy / tags | light | limited | explicit `tag-taxonomy` | wiki schema | limited | Tags/types should be part of page schema |
| Query | `kb-ask` + search | query pipeline | `wiki-query` | query skill | `wiki query` | Query should read graph nodes first |
| Lint / health | `kb-lint` | lint / doctor | `wiki-lint` | lint skill | `wiki lint` | Lint must check graph integrity and source attribution |
| Runtime state | config + search index | strongest: state DB | thin manifest | light schema | thin plugin state | TellMe should keep explicit state/runs outside repo data |
| Multi-host support | weak, Claude-first | weak to medium | strongest | strong | Claude-first | TellMe should combine runtime state with host-agnostic instructions |
| Data root configurability | weak global config | project/user config | `.env` / `OBSIDIAN_VAULT_PATH` | onboarding config | hardcoded-ish | TellMe must use env/config data root, never repo data dirs |

## Key Lessons

- From `llm-knowledge-base`: TellMe needs `reflect` and `merge` semantics even if they remain under the existing six commands. These are the missing bridge from source summaries to a living knowledge graph.
- From `obsidian-llm-wiki-local`: TellMe should keep a real Python runtime, explicit state, drafts, health checks, and auditable operations.
- From `obsidian-wiki`: TellMe must treat cross-linking, taxonomy, rebuild, and multi-host bootstrap as core capabilities, not optional prompts.
- From `second-brain`: TellMe should make onboarding and host-neutral instructions clear enough that Codex, Claude Code, and OpenCode can all follow the same project contract.
- From `llm-wiki-plugin`: TellMe should keep a single command surface and route richer behavior through command modes/policies instead of multiplying host-specific commands.

## Capability Gap In Current TellMe

Current TellMe has:

- External data root support after this cleanup.
- Auditable local commands.
- Static source registration.
- Deterministic source-summary compile.
- Codex handoff/consume for staged content.

Current TellMe still lacks:

- Knowledge-point extraction.
- Existing-node enrichment.
- New-node creation from concepts, entities, claims, and relationships.
- Graph edge extraction and maintenance.
- Contradiction detection and explanation candidates.
- LLM-assisted compare-against-vault behavior.
- Graph lint for source coverage, orphan concepts, duplicate concepts, and unresolved conflicts.

## Design Direction

TellMe should now be redesigned around a knowledge graph pipeline:

`raw evidence -> extracted claims/concepts -> graph alignment -> staged node/edge updates -> reviewed vault projection`

The vault should not be a mirror of raw documents. It should be the readable Obsidian projection of knowledge points and their relationships, with traceable source evidence.
