# Configuration

This page documents project configuration.

## MQTT environment file

Default path:

```text
/etc/homelab-ha-discovery/mqtt.env
```

Example:

```bash
HA_MQTT_HOST=192.168.4.27
HA_MQTT_PORT=1883
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
HA_MQTT_USERNAME=your-user
HA_MQTT_PASSWORD=your-password
```

## Host metrics config

Default path:

```text
/etc/homelab-ha-discovery/host-metrics.json
```

Use this file to control which publishers are enabled by the systemd installer.

## Device ID

Use a stable Home Assistant device ID, for example:

```bash
--ha-device-id hpc
```

Changing the device ID may create new Home Assistant entities.

## Expiry behavior

Publishers that support discovery may support:

```bash
--expire-after SECONDS
```

General behavior:

- `0` means no `expire_after`
- omitted in timer mode usually means `timer * 3`
- omitted in one-shot mode usually means no expiry
- negative, infinite, or NaN values should be rejected
