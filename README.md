# homelab-ha-discovery

![Python](https://img.shields.io/badge/Python-3-blue?logo=python)
![MQTT](https://img.shields.io/badge/MQTT-publisher-660066?logo=mqtt)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-discovery-41BDF5?logo=homeassistant)
![Debian](https://img.shields.io/badge/Debian-13-A81D33?logo=debian)
![License](https://img.shields.io/badge/License-MIT-green)

[English](README.md) | [繁體中文](README.zh-tw.md)

Expose homelab infrastructure metrics as Home Assistant MQTT entities automatically.

This project collects metrics from Debian hosts, Docker containers, Frigate, NVIDIA GPUs,
SMART disks/NVMe devices, Linux network interfaces, and ASUS routers, then publishes
Home Assistant MQTT discovery config plus metric state.

## Why this project?

Home Assistant can monitor homelab infrastructure, but writing MQTT discovery payloads
by hand is repetitive.

`homelab-ha-discovery` provides small Python publishers that:

- collect homelab metrics
- generate stable Home Assistant MQTT discovery entities
- publish metric state to MQTT
- make sensors appear automatically in Home Assistant

## Simple flow

```text
+-------------------+      collect       +---------------------+
| Debian host       | -----------------> | Python publisher    |
| Docker / Frigate  |                    | collector + parser  |
| ASUS router SSH   |                    +----------+----------+
+-------------------+                               |
                                                    | publish
                                                    v
                                         +---------------------+
                                         | MQTT broker         |
                                         | discovery + state   |
                                         +----------+----------+
                                                    |
                                                    v
                                         +---------------------+
                                         | Home Assistant      |
                                         | auto-created sensor |
                                         +---------------------+
```

## Supported metrics

| Area | Examples |
|---|---|
| CPU | usage, temperature |
| NVIDIA GPU | usage, memory usage, temperature |
| Disk SMART | power-on hours, temperature, reallocated/pending sectors |
| NVMe SMART | warning, spare, percentage used, temperature, written TB |
| Network | download/upload speed |
| Docker | state, health, restart count, CPU, memory, network |
| Frigate | system, camera, detector, GPU, storage metrics |
| ASUS router | CPU, temperature, network speed, connected clients |

## Requirements

- Python 3.10+
- MQTT broker reachable by Home Assistant
- Home Assistant MQTT integration enabled
- Linux host for most local collectors
- Optional: Docker, Frigate, NVIDIA tools, smartmontools, ASUS router SSH access

## Quick start

Clone the project:

```bash
git clone https://github.com/deepkh/homelab_ha_discovery.git
cd homelab_ha_discovery
```

Create a Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create MQTT config:

```bash
sudo mkdir -p /etc/homelab-ha-discovery
sudo editor /etc/homelab-ha-discovery/mqtt.env
```

Example:

```bash
HA_MQTT_HOST=192.168.4.27
HA_MQTT_PORT=1883
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
HA_MQTT_USERNAME=your-user
HA_MQTT_PASSWORD=your-password
```

Run one publisher manually:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc
```

## Recommended systemd install

Bootstrap config files:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc
```

Edit generated config:

```bash
sudo editor /etc/homelab-ha-discovery/mqtt.env
sudo editor /etc/homelab-ha-discovery/host-metrics.json
```

Install services from the managed copy:

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py install
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py enable --now
```

Check logs:

```bash
journalctl -u 'homelab-ha-discovery-*' -f
```

## Documentation

Detailed usage is kept outside the README so this page stays easy to read.

- [Systemd install](docs/install-systemd.md)
- [Configuration](docs/configuration.md)
- [Publishers](docs/publishers.md)
- [MQTT topics](docs/mqtt-topics.md)
- [Home Assistant](docs/home-assistant.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development](docs/development.md)

## Development

Run a quick syntax check:

```bash
python3 -m py_compile src/homelab_ha_discovery/**/*.py
```

Run tests when available:

```bash
pytest
```

## License

MIT


## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
