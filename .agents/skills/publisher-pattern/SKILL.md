---
name: publisher-pattern
description: Use when adding, changing, or refactoring metric publisher scripts, collectors, parser code, timer mode, publisher-only mode, or MQTT batching.
---

# Publisher pattern

## Separation

Keep collection/parsing code in:

```text
src/homelab_ha_discovery/collectors/
```

Keep runnable CLIs in:

```text
src/homelab_ha_discovery/scripts/
```

Shared MQTT/discovery/timer logic should stay reusable.

## CLI behavior

Publisher scripts should generally support:

- `--ha-device-id`
- `--publisher-only` when discovery is separable
- `--timer SECONDS` for long-running mode
- `--timer-publish-discovery-config SECONDS` when supported
- `--expire-after SECONDS` when Home Assistant discovery is supported
- `--debug` only when useful for troubleshooting

## MQTT behavior

One-shot publisher:

- collect metric
- prepare discovery config if needed
- prepare state payload
- publish batch through one MQTT connection

Timer publisher:

- keep one MQTT connection open
- publish each cycle as a batch
- handle baseline-sampled metrics carefully

## Error behavior

Exit before publishing discovery config or state when required metrics are missing,
unparsable, or unsafe.

## Validation

Run focused compile/test commands for changed files first.
