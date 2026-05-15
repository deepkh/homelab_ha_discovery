# MQTT topics

This page documents MQTT topic conventions.

## Prefix

Default topic prefix:

```text
homelab-ha-discovery
```

This may be configured with:

```bash
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
```

## Home Assistant discovery topics

Typical pattern:

```text
homeassistant/sensor/homelab_ha_discovery_<device>_<component>_<metric>/config
```

Discovery config messages should normally be retained.

## State topics

State topics depend on publisher type.

General expectation:

```text
<prefix>/<device>/<component>/state
```

Check the existing publisher before changing a topic.

GPU examples:

```text
homelab-ha-discovery/gpu/usages/<device>
homelab-ha-discovery/gpu/usages/<device>/gpu0
homelab-ha-discovery/gpu/amd_rocm/usages/<device>
homelab-ha-discovery/gpu/amd_rocm/usages/<device>/gpu0
homelab-ha-discovery/gpu/intel_qsv/usages/<device>
homelab-ha-discovery/gpu/intel_qsv/usages/<device>/gpu0
```

NVIDIA keeps the original GPU topic shape. AMD ROCm and Intel QSV include the
collector name to avoid collisions when a host publishes multiple GPU backends.

Container examples:

```text
homelab-ha-discovery/hpc/docker/plex/metrics
homelab-ha-discovery/hpc/podman/root/plex/metrics
homelab-ha-discovery/hpc/podman/alice/plex/metrics
```

Podman topics include a scope segment so root containers and rootless users do not
share MQTT state topics or Home Assistant discovery IDs.

## Stability rule

Do not casually change:

- discovery topic
- state topic
- `unique_id`
- device identifiers

Changing these can create duplicate entities in Home Assistant.
