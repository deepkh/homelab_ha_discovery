# AGENTS.md

## Project purpose

This repository provides Python MQTT publishers for homelab metrics with Home Assistant
MQTT discovery.

The goal is stable Home Assistant entities for Debian host metrics, Docker containers,
Frigate metrics, Linux network interfaces, SMART/NVMe health, NVIDIA GPUs, and ASUS
router metrics collected over SSH.

## Load only relevant detail

Do not read every detailed rule before every task.

Use this file as the routing portal. For task-specific behavior, select the matching
skill under `.agents/skills/`.

## Important paths

```text
src/homelab_ha_discovery/
├── collectors/   # metric collection and parsing
├── scripts/      # runnable publisher and installer CLIs
├── mqtt.py       # MQTT helpers
├── discovery.py  # Home Assistant MQTT discovery helpers
└── ...
tests/            # tests when present
docs/             # human documentation
.agents/skills/   # task-specific Codex skills
```

## Common commands

```bash
python3 -m py_compile src/homelab_ha_discovery/**/*.py
pytest
```

Use narrower validation first when possible.

## Safety rules

- Do not store MQTT credentials in the repository.
- Do not publish test MQTT messages unless explicitly asked.
- Do not run `sudo smartctl` on real disks unless explicitly asked.
- Do not run SSH commands against routers or homelab servers unless explicitly asked.
- Do not stop containers or systemd services unless explicitly asked.
- Ask before destructive commands such as deleting files or rewriting git history.
- Prefer small, reviewable diffs.
- Do not add dependencies unless asked.
- Do not update `requirements.txt` unless asked.

## Skill routing

Use these skills when relevant:

- `.agents/skills/project-maintenance/SKILL.md`
  - repo-wide conventions, validation, small-diff policy

- `.agents/skills/ha-mqtt-discovery/SKILL.md`
  - Home Assistant MQTT discovery topics, unique IDs, device/entity rules

- `.agents/skills/publisher-pattern/SKILL.md`
  - adding or modifying publisher scripts and collectors

- `.agents/skills/systemd-installer/SKILL.md`
  - bootstrap, detect, install, enable, logs, restart, uninstall behavior

- `.agents/skills/docker-frigate/SKILL.md`
  - Docker container metrics and Frigate metrics

- `.agents/skills/asus-router/SKILL.md`
  - ASUS router SSH collectors and parser behavior

- `.agents/skills/docs-sync/SKILL.md`
  - README, README.zh-tw, docs update rules

## Documentation rule

When behavior, commands, topics, environment variables, setup, or user-facing usage
changes, check whether documentation must be updated.

Keep `README.md` concise and human-readable. Put detailed references in `docs/`.
