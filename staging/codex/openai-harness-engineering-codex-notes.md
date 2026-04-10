---
page_type: synthesis
status: staged
sources: [raw/openai-harness-engineering.md]
last_host: codex
---

# Harness Engineering: Codex Collaboration Notes

## TellMe Seed Notes

- The article frames Codex-oriented engineering as environment design: humans define intent, constraints, tools, and feedback loops while agents execute implementation work.
- A major operational lesson is that repository-local, versioned documentation is more useful to agents than large transient prompts or external context.
- The workflow implications map directly onto TellMe: source material should enter `raw/`, derived knowledge should become inspectable Markdown, and agent output should be staged before becoming canonical.
- The article reinforces TellMe's current MVP direction: keep host work auditable, encode boundaries mechanically, and make the repo itself the record system.

## Candidate Links

- [[openai-harness-engineering]]
