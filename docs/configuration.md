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

### Podman container services

Podman services use `publish_podman_container_metrics.py`. Root Podman uses the
`root` scope:

```json
{
  "type": "podman_containers",
  "enabled": true,
  "scope": "root",
  "include_label": "homelab-ha-discovery.enabled=true",
  "podman_command": "podman",
  "timer": 60.0,
  "expire_after": null
}
```

Rootless Podman services run as the configured user. The installer writes
`User=<rootless_user>` and `XDG_RUNTIME_DIR=/run/user/<rootless_uid>` into the
generated unit:

```json
{
  "type": "podman_containers",
  "enabled": true,
  "scope": "alice",
  "rootless_user": "alice",
  "rootless_uid": 1001,
  "include_label": "homelab-ha-discovery.enabled=true",
  "podman_command": "podman",
  "timer": 60.0,
  "expire_after": null
}
```

Podman service options:

- `scope` keeps root and rootless MQTT topics/entities distinct.
- `rootless_user` enables rootless systemd unit rendering.
- `rootless_uid` is optional when the user exists on the install host, but
  detected configs include it for repeatability.
- `all` passes `--all` to include stopped containers.
- Detected Podman configs default to
  `include_label: homelab-ha-discovery.enabled=true`, matching Docker, so users
  opt containers into publishing by label.
- `include_label` and `include_labels` pass repeated `--include-label` filters.
- `podman_command` can point to an absolute Podman CLI path.

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
