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
```

NVIDIA keeps the original GPU topic shape. AMD ROCm includes the collector name
to avoid collisions when a host publishes multiple GPU backends.

## Stability rule

Do not casually change:

- discovery topic
- state topic
- `unique_id`
- device identifiers

Changing these can create duplicate entities in Home Assistant.
