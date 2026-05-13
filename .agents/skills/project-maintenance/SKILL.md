---
name: project-maintenance
description: Use when making repo-wide changes, refactoring, validating, editing project structure, or applying general development conventions.
---

# Project maintenance

## Goals

Keep changes small, reviewable, and safe for a homelab monitoring project.

## General rules

- Inspect existing code before changing conventions.
- Prefer minimal diffs.
- Do not add dependencies unless asked.
- Do not update `requirements.txt` unless asked.
- Do not store credentials in the repository.
- Keep CLI behavior backward-compatible when possible.

## Validation

Use focused validation first.

```bash
python3 -m py_compile src/homelab_ha_discovery/**/*.py
pytest
```

If changing only one script, a targeted compile check is preferred before broad checks.

## Documentation

When user-facing behavior changes, check whether these need updates:

- `README.md`
- `README.zh-tw.md`
- `docs/`
- relevant `.agents/skills/*/SKILL.md`

## Safety

Do not run commands that touch real homelab services unless explicitly asked:

- stopping containers
- restarting systemd services
- publishing MQTT test payloads
- running SSH commands against routers
- running `sudo smartctl` on real disks
