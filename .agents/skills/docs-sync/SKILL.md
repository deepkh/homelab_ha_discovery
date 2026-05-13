---
name: docs-sync
description: Use when editing README, README.zh-tw, docs, AGENTS.md, or keeping human docs and Codex agent instructions synchronized.
---

# Documentation sync

## README role

`README.md` is for humans.

Keep it:

- clear
- simple
- short
- easy to scan
- focused on purpose, flow, supported metrics, quick start, and links

Avoid putting long references in README.

Move details to `docs/`.

## README.zh-tw role

`README.zh-tw.md` should track the same structure as `README.md`,
but it does not need to be a word-for-word translation.

Use Traditional Chinese with common technical terms left in English when clearer.

## AGENTS.md role

`AGENTS.md` is a short Codex routing portal.

Do not put all detailed rules in AGENTS.md.

Point to `.agents/skills/*/SKILL.md` instead.

## Docs role

Use `docs/` for detailed human documentation:

- install-systemd.md
- configuration.md
- publishers.md
- mqtt-topics.md
- home-assistant.md
- troubleshooting.md
- development.md

## Checklist

Before finishing documentation changes:

- README remains short.
- README and README.zh-tw have similar structure.
- Detailed references live in docs.
- AGENTS.md remains a portal, not a full manual.
- Relevant skill files are updated if agent behavior changed.
