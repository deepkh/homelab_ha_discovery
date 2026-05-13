# Home Assistant

## MQTT integration

Home Assistant must have the MQTT integration enabled and connected to the same broker
used by this project.

## Entity creation

Entities are created through Home Assistant MQTT discovery.

General flow:

```text
publisher -> MQTT discovery config -> Home Assistant creates entity
publisher -> MQTT state payload     -> Home Assistant updates state
```

## Troubleshooting entity creation

If entities do not appear:

1. Confirm MQTT broker connectivity.
2. Confirm Home Assistant MQTT integration is connected.
3. Check discovery config topic in MQTT Explorer.
4. Check state topic in MQTT Explorer.
5. Confirm the discovery config `state_topic` matches the actual state topic.
6. Check Home Assistant logs.

## Avoid duplicate entities

Use stable values for:

- `--ha-device-id`
- MQTT topic prefix
- entity unique IDs
- device identifiers
