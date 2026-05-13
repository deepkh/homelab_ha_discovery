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

### GPU services

GPU services use the shared `publish_gpu_metrics.py` publisher. The `collector`
selects the backend:

- `nvidia` uses `nvidia-smi`
- `amd_rocm` uses `rocm-smi`

Example NVIDIA service publishing two selected cards in one timer loop:

```json
{
  "type": "gpu",
  "enabled": true,
  "collector": "nvidia",
  "gpu_indexes": [0, 1],
  "timer": 5.0,
  "expire_after": null
}
```

Example AMD ROCm service:

```json
{
  "type": "gpu",
  "enabled": true,
  "collector": "amd_rocm",
  "gpu_indexes": [0],
  "timer": 5.0,
  "expire_after": null
}
```

Compatibility notes:

- Omit `gpu_indexes` to publish all cards returned by the collector.
- Use `gpu_indexes` for multiple cards in one service.
- Existing `gpu_index` configs still work for a single card.
- Do not set both `gpu_index` and `gpu_indexes`.

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
