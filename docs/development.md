# Development

## Quick validation

```bash
python3 -m py_compile src/homelab_ha_discovery/**/*.py
pytest
```

## Recommended change style

- Prefer small, reviewable diffs.
- Keep collectors separate from CLI scripts.
- Avoid changing MQTT topics or unique IDs unless necessary.
- Avoid adding dependencies unless there is a clear reason.
- Update docs when user-facing behavior changes.

## Suggested code organization

```text
src/homelab_ha_discovery/
├── collectors/
├── scripts/
├── mqtt.py
├── discovery.py
└── ...
```

## Documentation locations

- `README.md`: short human landing page
- `README.zh-tw.md`: short Traditional Chinese landing page
- `docs/`: detailed human documentation
- `AGENTS.md`: short Codex routing portal
- `.agents/skills/`: detailed Codex skills
