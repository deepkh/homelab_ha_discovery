# homelab-ha-discovery

![Python](https://img.shields.io/badge/Python-3-blue?logo=python)
![MQTT](https://img.shields.io/badge/MQTT-publisher-660066?logo=mqtt)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-discovery-41BDF5?logo=homeassistant)
![Debian](https://img.shields.io/badge/Debian-13-A81D33?logo=debian)
![License](https://img.shields.io/badge/License-MIT-green)

[English](README.md) | [繁體中文](README.zh-tw.md)

Python MQTT publishers for homelab metrics with Home Assistant MQTT discovery.

The current runnable publishers collect metrics from the local Debian host and publish JSON payloads to MQTT. Normal runs publish retained Home Assistant discovery config first, then publish the current metric state. External systemd timer runs can use `--publisher-only` after discovery has already been registered. Long-running service mode is also available with `--timer SECONDS`.

For AI agent and repository maintenance rules, see [AGENTS.md](AGENTS.md).

## Requirements

- Python 3 runtime
- `paho-mqtt`, installed from `requirements.txt`
- `top` for CPU usage publishing
- `nvidia-smi` for NVIDIA GPU publishing
- MQTT broker access

## Setup

These instructions are for human operators.

### Install Python 3

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl ca-certificates
```

### Create Python 3 virtual environment

Only if `.venv/` does not exist or is empty, create the virtual environment with:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install necessary libs to `.venv` for Python 3 (optional)

```bash
pip install paho-mqtt
```

### Install necessary libs from `requirements.txt`

```bash
pip install -r requirements.txt
```

### Dump `.venv/` installed libs to `requirements.txt`

```bash
pip freeze > requirements.txt
```

## Configuration

The scripts read MQTT settings from the environment and also try to load `/etc/homelab-ha-discovery/mqtt.env`.

Supported environment variables:

- `HA_MQTT_HOST`, default `mqtt-server-ip`
- `HA_MQTT_PORT`, default `1833`
- `HA_MQTT_TOPIC_PREFIX`, default `homelab-ha-discovery`
- `HA_MQTT_USERNAME`, optional MQTT username
- `HA_MQTT_PASSWORD`, optional MQTT password
- `HA_MQTT_CLIENT_ID`, optional MQTT client ID
- `MQTT_TOPIC`, optional state-topic override

Do not store MQTT credentials in this repository. For systemd services or timers, prefer an environment file outside the repo, for example `/etc/homelab-ha-discovery/mqtt.env`, readable only by the service user or root.

Example environment file:

```bash
HA_MQTT_HOST=mqtt-server-ip
HA_MQTT_PORT=1833
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
HA_MQTT_USERNAME=your-user
HA_MQTT_PASSWORD=your-password
```

## Usage

Run from the repository root.

CPU usage:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc
```

NVIDIA GPU metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc
```

For frequent systemd timer runs, use `--publisher-only` after a normal run has registered discovery config:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --publisher-only
```

For long-running service mode, use `--timer SECONDS`. The first metric publish happens immediately, then the script sleeps between publish attempts:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0
```

Without `--publisher-only`, `--timer` publishes discovery config once at startup, then publishes only metric state each interval. With `--timer --publisher-only`, it publishes only metric state each interval.

To republish retained discovery config periodically during long-running service mode, add `--timer-publish-discovery-config SECONDS`:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
```

If `--timer-publish-discovery-config` is not set, timer behavior stays discovery-once. This option requires `--timer` and cannot be combined with `--publisher-only`.

The hidden `--host` argument is accepted as a compatibility alias for `--device`.

## MQTT Topics

With the default topic prefix and `--device hpc`, CPU usage publishes state to:

```text
homelab-ha-discovery/cpu/usages/hpc
```

Payload:

```json
{"CPU Usages":37.8}
```

Discovery topic:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_cpu_usage/config
```

NVIDIA GPU metrics publish state to:

```text
homelab-ha-discovery/gpu/usages/hpc
```

Payload:

```json
{"GPU Usages":65.0,"Memory Usage":48.3}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_gpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_gpu_memory_usage/config
```

Discovery config is retained. Metric state is non-retained by default.

## Development

Collectors live in `src/homelab_ha_discovery/collectors/`; runnable scripts live in `src/homelab_ha_discovery/scripts/`.

Relevant validation commands:

```bash
python3 -m py_compile src/homelab_ha_discovery/mqtt.py
python3 -m py_compile src/homelab_ha_discovery/scripts/timer.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_cpu_usage.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_gpu_metrics.py
```

Run `pytest` if tests are present.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
