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
- `paho-mqtt` for MQTT and `psutil` for Linux network interface throughput, installed from `requirements.txt`
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
pip install paho-mqtt psutil
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
- `HA_MQTT_PORT`, default `1883`
- `HA_MQTT_TOPIC_PREFIX`, default `homelab-ha-discovery`
- `HA_MQTT_USERNAME`, optional MQTT username
- `HA_MQTT_PASSWORD`, optional MQTT password
- `HA_MQTT_CLIENT_ID`, optional MQTT client ID
- `MQTT_TOPIC`, optional state-topic override

Do not store MQTT credentials in this repository. For systemd services or timers, prefer an environment file outside the repo, for example `/etc/homelab-ha-discovery/mqtt.env`, readable only by the service user or root.

Example environment file:

```bash
HA_MQTT_HOST=mqtt-server-ip
HA_MQTT_PORT=1883
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
HA_MQTT_USERNAME=your-user
HA_MQTT_PASSWORD=your-password
```

## Clean Host Systemd Installer

A clean Debian host can be bootstrapped from a checkout with:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc
```

`bootstrap` copies the current checkout to `/opt/homelab-ha-discovery`, refuses
to replace that directory unless `--force-copy` is passed, creates
`/opt/homelab-ha-discovery/.venv`, installs `requirements.txt`, creates
`/etc/homelab-ha-discovery`, and writes a reviewable
`/etc/homelab-ha-discovery/host-metrics.json`. The copy excludes `.git`,
`.venv`, caches, and local session artifacts.

Debian package installation is opt-in:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc --install-system-packages
```

If `/etc/homelab-ha-discovery/mqtt.env` is missing, `bootstrap` creates it with
editable example settings and mode `600`, then prints a warning. Edit the file
before enabling services:

```bash
sudo editor /etc/homelab-ha-discovery/mqtt.env
sudo editor /etc/homelab-ha-discovery/host-metrics.json
```

After reviewing the detected metrics config, generate and enable long-running
systemd services:

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py install
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py enable --now
python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py status
```

Generated units use `EnvironmentFile=-/etc/homelab-ha-discovery/mqtt.env`, but
`enable --now` refuses to enable/start services when the real env file is
missing unless `--allow-missing-mqtt-env` is passed. The units run the existing
publishers in long-running `--timer` mode. Default intervals are CPU and GPU
`5.0` seconds, disk and NVMe SMART `60.0` seconds, and network `1.0` second.
Generated `host-metrics.json` also includes a top-level
`timer_publish_discovery_config` default of `60.0`, so generated services
republish retained Home Assistant discovery config every 60 seconds. Set it to
`null` to disable that globally, or add `timer_publish_discovery_config` to an
individual service entry to override it for that service.

The installer does not configure sudoers. Disk and NVMe SMART publishers run
`sudo smartctl -a <dev>`, so configure non-interactive sudo permission for the
service user when those services will not run as root.

For a harmless preview, pass `--dry-run`. For tests or non-default layouts, the
installer subcommands also accept `--app-dir`, `--config-dir`, and
`--systemd-dir`.

## Usage

Run from the repository root.

Pass `--ha-device-id` as the stable Home Assistant/MQTT device identity. It is
used in MQTT topics, Home Assistant unique IDs, device identifiers, and sensor
names. Keep it stable to avoid duplicate Home Assistant entities. `--dev` is
separate and still names the disk path, NVMe controller path, or network
interface component where a publisher needs one.

CPU metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc
```

NVIDIA GPU metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc
```

When `--gpu` is omitted, all detected NVIDIA GPUs are published as `gpu0`,
`gpu1`, and so on in `nvidia-smi` row order. To publish only one GPU, pass its
zero-based index:

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --gpu 0
```

Disk SMART metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda
```

The disk SMART publisher runs `sudo smartctl -a <dev>` locally. Configure sudo
outside this repository so the service user can run the required `smartctl`
command non-interactively. The disk component in MQTT and Home Assistant
discovery is derived from the `--dev` basename, for example `sda` for
`/dev/sda`.

NVMe SMART metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0
```

The NVMe SMART publisher also runs `sudo smartctl -a <dev>` locally. Run one
process or service per NVMe controller, for example `/dev/nvme0`, `/dev/nvme1`,
and so on. The NVMe component in MQTT and Home Assistant discovery is derived
from the `--dev` basename, for example `nvme0` for `/dev/nvme0`.

Network metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0
```

The network publisher uses `psutil.net_io_counters(pernic=True)` locally.
`--dev` must match a network interface key, for example `ppp0`. Without
`--timer`, it takes two samples one second apart and publishes one calculated
throughput state. Speeds are published in `KB/s`, where `KB` means 1024 bytes,
and values are rounded to two decimal places.

For frequent systemd timer runs, use `--publisher-only` after a normal run has registered discovery config:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --publisher-only
```

For long-running service mode, use `--timer SECONDS`. Most publishers publish
the first metric immediately, then sleep between publish attempts. Network
metrics establish a baseline first, wait one interval, then publish the first
calculated speed:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --timer 1.0
```

Without `--publisher-only`, `--timer` publishes discovery config once at
startup, then publishes only metric state each interval. For network metrics,
the startup discovery config is published before the first calculated metric
state after the baseline interval. With `--timer --publisher-only`, it publishes
only metric state each interval.

To republish retained discovery config periodically during long-running service mode, add `--timer-publish-discovery-config SECONDS`:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --timer 1.0 --timer-publish-discovery-config 60.0
```

If `--timer-publish-discovery-config` is not set, timer behavior stays discovery-once. This option requires `--timer` and cannot be combined with `--publisher-only`.

## MQTT Topics

With the default topic prefix and `--ha-device-id hpc`, CPU metrics publish state to:

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

With `--ha-device-id hpc`, NVIDIA GPU metrics publish state to this topic when
`--gpu` is omitted:

```text
homelab-ha-discovery/gpu/usages/hpc
```

Payload:

```json
{"gpu0":{"GPU Card Name":"NVIDIA GeForce RTX 5060 Ti","GPU Usages":55.2,"Memory Usage":41.7,"Temperature":72},"gpu1":{"GPU Card Name":"NVIDIA GeForce RTX 3060","GPU Usages":30.0,"Memory Usage":22.5,"Temperature":61},"gpu2":{"GPU Card Name":"NVIDIA RTX A4000","GPU Usages":80.4,"Memory Usage":70.1,"Temperature":68}}
```

With `--ha-device-id hpc --gpu 0`, NVIDIA GPU metrics publish only `gpu0` to:

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

With `--ha-device-id hpc --dev /dev/sda`, disk SMART metrics publish state to:

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

With `--ha-device-id hpc --dev /dev/nvme0`, NVMe SMART metrics publish state to:

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

With `--ha-device-id hpc --dev ppp0`, network metrics publish state to:

```text
homelab-ha-discovery/ppp0/metrics/hpc
```

Payload:

```json
{"Download Speed":123.45,"Upload Speed":67.89}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_ppp0_download_speed/config
homeassistant/sensor/homelab_ha_discovery_hpc_ppp0_upload_speed/config
```

Network speed sensors use `KB/s`, where `KB` means 1024 bytes. The Home
Assistant sensor names also use the network interface component, for example
`hpc ppp0 Download Speed`. Because the interface component is included in Home
Assistant unique IDs, changing `--dev` changes the entities.

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
python3 -m py_compile src/homelab_ha_discovery/collectors/network_linux.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_network_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/install_debian_host_systemd.py
```

Run `pytest` if tests are present.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
