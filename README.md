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
- `top` and `sensors` for CPU metrics publishing. On Debian, `sensors` is provided by `lm-sensors`.
- `nvidia-smi` for NVIDIA GPU publishing
- `smartctl` for disk and NVMe SMART publishing. On Debian, `smartctl` is provided by `smartmontools`.
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

CPU metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc
```

NVIDIA GPU metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc
```

When `--gpu` is omitted, all detected NVIDIA GPUs are published as `gpu0`,
`gpu1`, and so on in `nvidia-smi` row order. To publish only one GPU, pass its
zero-based index:

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --gpu 0
```

Disk SMART metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda
```

The disk SMART publisher runs `sudo smartctl -a <dev>` locally. Configure sudo
outside this repository so the service user can run the required `smartctl`
command non-interactively. The disk component in MQTT and Home Assistant
discovery is derived from the `--dev` basename, for example `sda` for
`/dev/sda`.

NVMe SMART metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0
```

The NVMe SMART publisher also runs `sudo smartctl -a <dev>` locally. Run one
process or service per NVMe controller, for example `/dev/nvme0`, `/dev/nvme1`,
and so on. The NVMe component in MQTT and Home Assistant discovery is derived
from the `--dev` basename, for example `nvme0` for `/dev/nvme0`.

For frequent systemd timer runs, use `--publisher-only` after a normal run has registered discovery config:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0 --publisher-only
```

For long-running service mode, use `--timer SECONDS`. The first metric publish happens immediately, then the script sleeps between publish attempts:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0 --timer 5.0
```

Without `--publisher-only`, `--timer` publishes discovery config once at startup, then publishes only metric state each interval. With `--timer --publisher-only`, it publishes only metric state each interval.

To republish retained discovery config periodically during long-running service mode, add `--timer-publish-discovery-config SECONDS`:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0 --timer 5.0 --timer-publish-discovery-config 60.0
```

If `--timer-publish-discovery-config` is not set, timer behavior stays discovery-once. This option requires `--timer` and cannot be combined with `--publisher-only`.

The hidden `--host` argument is accepted as a compatibility alias for `--device`.

## MQTT Topics

With the default topic prefix and `--device hpc`, CPU metrics publish state to:

```text
homelab-ha-discovery/cpu/metrics/hpc
```

Payload:

```json
{"CPU Usages":37.8,"Temperature":54.0}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_cpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_cpu_temperature/config
```

NVIDIA GPU metrics publish state to this topic when `--gpu` is omitted:

```text
homelab-ha-discovery/gpu/usages/hpc
```

Payload:

```json
{"gpu0":{"GPU Card Name":"NVIDIA GeForce RTX 5060 Ti","GPU Usages":55.2,"Memory Usage":41.7,"Temperature":72},"gpu1":{"GPU Card Name":"NVIDIA GeForce RTX 3060","GPU Usages":30.0,"Memory Usage":22.5,"Temperature":61},"gpu2":{"GPU Card Name":"NVIDIA RTX A4000","GPU Usages":80.4,"Memory Usage":70.1,"Temperature":68}}
```

With `--gpu 0`, NVIDIA GPU metrics publish only `gpu0` to:

```text
homelab-ha-discovery/gpu/usages/hpc/gpu0
```

Payload:

```json
{"gpu0":{"GPU Card Name":"NVIDIA GeForce RTX 5060 Ti","GPU Usages":55.2,"Memory Usage":41.7,"Temperature":72}}
```

Discovery topics are published for every GPU included in that run:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_gpu0_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_gpu0_memory_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_gpu0_temperature/config
```

`GPU Card Name` is included as payload metadata only; no Home Assistant sensor is
created for it.

With `--dev /dev/sda`, disk SMART metrics publish state to:

```text
homelab-ha-discovery/sda/metrics/hpc
```

Payload:

```json
{"Power On Hours":3103,"Temperature":42,"Reallocated Sectors":0,"Pending Sectors":0}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_sda_power_on_hours/config
homeassistant/sensor/homelab_ha_discovery_hpc_sda_temperature/config
homeassistant/sensor/homelab_ha_discovery_hpc_sda_reallocated_sectors/config
homeassistant/sensor/homelab_ha_discovery_hpc_sda_pending_sectors/config
```

The Home Assistant sensor names also use the disk component, for example
`hpc sda Power On Hours`. Because the disk component is included in Home
Assistant unique IDs, changing `--dev` changes the entities.

With `--dev /dev/nvme0`, NVMe SMART metrics publish state to:

```text
homelab-ha-discovery/nvme0/metrics/hpc
```

Payload:

```json
{"Critical Warning":0,"Media and Data Integrity Errors":0,"Available Spare":100,"Percentage Used":3,"Critical Temperature Time":0,"temperature_c":35,"data_written_tb":5.06,"power_on_hours":6528}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_critical_warning/config
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_media_data_integrity_errors/config
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_available_spare/config
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_percentage_used/config
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_critical_temperature_time/config
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_temperature_c/config
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_data_written_tb/config
homeassistant/sensor/homelab_ha_discovery_hpc_nvme0_power_on_hours/config
```

The Home Assistant sensor names also use the NVMe component, for example
`hpc nvme0 Available Spare`. Because the NVMe component is included in Home
Assistant unique IDs, run one publisher per controller to keep entities stable.
`Available Spare` and `Percentage Used` use `%`; `Critical Temperature Time`
uses `min`; `temperature_c` uses `°C`; `power_on_hours` uses `h`;
`data_written_tb` uses `TB`; warning and error metrics are unitless.

If `MQTT_TOPIC` is set, publishers use it as the state topic and discovery config
points to that exact topic.

Discovery config is retained. Metric state is non-retained by default.

## Development

Collectors live in `src/homelab_ha_discovery/collectors/`; runnable scripts live in `src/homelab_ha_discovery/scripts/`.

Relevant validation commands:

```bash
python3 -m py_compile src/homelab_ha_discovery/mqtt.py
python3 -m py_compile src/homelab_ha_discovery/scripts/timer.py
python3 -m py_compile src/homelab_ha_discovery/collectors/cpu_sensors.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_cpu_metrics.py
python3 -m py_compile src/homelab_ha_discovery/collectors/gpu_nvidia.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_gpu_metrics.py
python3 -m py_compile src/homelab_ha_discovery/collectors/disk_smart.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_sdx_metrics.py
python3 -m py_compile src/homelab_ha_discovery/collectors/nvme_smart.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_nvme_metrics.py
```

Run `pytest` if tests are present.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
