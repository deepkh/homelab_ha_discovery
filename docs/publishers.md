# Publishers

Publishers are CLI scripts that collect metrics and publish MQTT discovery/state messages.

## Common pattern

```text
+--------------+      +-------------+      +------------------+
| CLI options  | ---> | collector   | ---> | MQTT publisher   |
+--------------+      +-------------+      +------------------+
                             |
                             v
                      normalized metric
```

## Common CLI options

Many publisher scripts support options like:

```bash
--ha-device-id DEVICE_ID
--timer SECONDS
--expire-after SECONDS
--publisher-only
--debug
```

Check each script for exact support.

## One-shot mode

One-shot mode usually:

1. collects metrics once
2. publishes discovery config when needed
3. publishes one state payload
4. exits

## Timer mode

Timer mode usually:

1. opens one MQTT connection
2. collects metrics repeatedly
3. publishes state payloads every cycle
4. periodically republishes discovery config when configured

## GPU publisher

`publish_gpu_metrics.py` is shared by the GPU collectors.

Backends:

- `--collector nvidia` reads NVIDIA metrics from `nvidia-smi`
- `--collector amd_rocm` reads AMD ROCm metrics from `rocm-smi`
- `--collector intel_qsv` reads Intel media engine metrics from `intel_gpu_top -J`

Published NVIDIA/AMD metrics per GPU card:

- GPU usage percent
- memory usage percent
- temperature in Celsius

Published Intel QSV metrics:

- Render/3D engine busy percent
- Blitter engine busy percent
- Video engine busy percent
- VideoEnhance engine busy percent
- Compute engine busy percent
- QSV active
- QSV available

Examples:

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --collector amd_rocm
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --collector intel_qsv
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --gpu 0 --gpu 1
```

When `--gpu` is repeated, the selected cards are collected and published in one
state payload for that timer cycle. Without `--gpu`, the publisher publishes all
cards returned by the selected collector.

## Container publishers

Docker and Podman container publishers report the same metric set:

- state
- health
- restart count
- CPU usage percent
- memory usage, limit, and percent
- download/upload speed

Docker example:

```bash
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc
```

Podman root example:

```bash
python3 src/homelab_ha_discovery/scripts/publish_podman_container_metrics.py --ha-device-id hpc --podman-scope root
```

Podman rootless example when run as that user:

```bash
python3 src/homelab_ha_discovery/scripts/publish_podman_container_metrics.py --ha-device-id hpc --podman-scope alice
```

The systemd installer renders rootless Podman units with `User=` and
`XDG_RUNTIME_DIR=` when `rootless_user` is set in `host-metrics.json`.
Detected Docker and Podman service configs default to
`include_label: homelab-ha-discovery.enabled=true`, so containers are published
only after being opted in with that label.

Podman rootless networking may not expose network counters through `podman stats`.
When Podman reports `-- / --` for network I/O, the publisher emits zero network
speed instead of failing the publish cycle.

## Adding a publisher

Recommended structure:

- Put collection/parsing code under `src/homelab_ha_discovery/collectors/`
- Put runnable CLI code under `src/homelab_ha_discovery/scripts/`
- Reuse shared MQTT/discovery helpers
- Keep Home Assistant unique IDs stable
- Add or update docs when user-facing behavior changes
