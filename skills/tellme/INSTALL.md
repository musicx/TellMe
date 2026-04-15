# Installing the `tellme` skill

The canonical skill lives in this repo at `skills/tellme/SKILL.md`. Claude Code loads skills from `~/.claude/skills/<name>/SKILL.md`, so installing is a one-time wrapper setup.

Two options:

## Option 1 — Symlink (recommended)

```bash
mkdir -p ~/.claude/skills/tellme
ln -sf "$(pwd)/skills/tellme/SKILL.md" ~/.claude/skills/tellme/SKILL.md
```

Edits to `skills/tellme/SKILL.md` in this repo are picked up immediately.

## Option 2 — Wrapper file (if you don't want symlinks)

Create `~/.claude/skills/tellme/SKILL.md` with:

```markdown
---
name: tellme
description: Use when the user asks you to ingest sources, compile a knowledge graph, review staged pages, query the wiki, publish content, or reconcile drift in a TellMe project.
---

# tellme

This is a wrapper. Read the canonical source before doing anything else:

- `<absolute path to this repo>/skills/tellme/SKILL.md`

Follow the canonical source as the real skill contract.
```

When the repo changes, re-copy the canonical file into `~/.claude/skills/tellme/SKILL.md`.

## Verifying

In Claude Code, ask "list my skills" or start a session inside the TellMe project — the `tellme` skill should surface when you mention ingest, compile, publish, query, lint, reconcile, or reader-rewrite.
