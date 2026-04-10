# Unit 5 Checkpoint: Static Lint

## Scope

- Unit: Unit 5 Static Lint And Reconcile Foundation
- Sub-slice: static lint only

## Completed

- Added minimal frontmatter parsing.
- Added Obsidian wikilink extraction.
- Added static vault lint checks for missing frontmatter, missing sources, and broken wikilinks.
- Wired `tellme lint` to static lint behavior.

## Verification

- `python -m pytest tests/test_linting.py tests/test_cli.py -q` -> 7 passed in 1.49s
- `python -m pytest tests -q` -> 25 passed in 2.32s

## Next

- Continue Unit 5 reconcile sub-slice.

## Stop Condition

- If reconcile requires publishing policy or automatic merge semantics beyond drift detection and safe state update, stop and return to planning.
