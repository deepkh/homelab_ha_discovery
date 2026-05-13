---
name: ha-mqtt-discovery
description: Use when changing Home Assistant MQTT discovery config, MQTT topics, unique IDs, device identifiers, expire_after, retained discovery config, or sensor naming.
---

# Home Assistant MQTT discovery rules

## Core rules

- Use stable Home Assistant `unique_id` values.
- Include device, component, and metric identity in unique IDs.
- Keep device identifiers stable to avoid duplicate Home Assistant entities.
- Discovery config messages are retained.
- Metric state messages are not retained by default.
- Discovery config must point to the exact state topic used by the publisher.

## Topic conventions

Default topic prefix:

```text
homelab-ha-discovery
```

Typical discovery topic pattern:

```text
homeassistant/sensor/homelab_ha_discovery_<device>_<component>_<metric>/config
```

State topic pattern depends on publisher type. Check existing publisher behavior before changing it.

## expire_after

Publishers that support Home Assistant discovery should support:

```bash
--expire-after SECONDS
```

Rules:

- Reject negative, infinite, and NaN values.
- `--expire-after 0` means omit `expire_after`.
- In timer mode, omitted `--expire-after` defaults to `timer * 3`.
- In one-shot mode, omitted `--expire-after` means no expiry.
- Write `expire_after` as an integer ceiling when effective.

## Validation checklist

Before finishing:

- Check unique IDs are stable.
- Check discovery topic matches naming convention.
- Check value template reads the actual JSON payload.
- Check state topic in discovery equals publisher state topic.
- Check README/docs if user-facing behavior changed.
