# homelab-ha-discovery

![Python](https://img.shields.io/badge/Python-3-blue?logo=python)
![MQTT](https://img.shields.io/badge/MQTT-publisher-660066?logo=mqtt)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-discovery-41BDF5?logo=homeassistant)
![Debian](https://img.shields.io/badge/Debian-13-A81D33?logo=debian)
![License](https://img.shields.io/badge/License-MIT-green)

[English](README.md) | [繁體中文](README.zh-tw.md)

Python MQTT publishers for homelab metrics with Home Assistant MQTT discovery.

The current runnable publishers collect metrics from the local Debian host, local Docker containers, and ASUS routers over SSH, then publish JSON payloads to MQTT. Normal runs publish retained Home Assistant discovery config first, then publish the current metric state. External systemd timer runs can use `--publisher-only` after discovery has already been registered. Long-running service mode is also available with `--timer SECONDS`.

For AI agent and repository maintenance rules, see [AGENTS.md](AGENTS.md).

## Requirements

- Python 3 runtime
- `paho-mqtt` for MQTT and `psutil` for Linux network interface throughput, installed from `requirements.txt`
- `top` and `sensors` for CPU metrics publishing. On Debian, `sensors` is provided by `lm-sensors`.
- `nvidia-smi` for NVIDIA GPU publishing
- `smartctl` for disk and NVMe SMART publishing. On Debian, `smartctl` is provided by `smartmontools`.
- Docker CLI access for Docker container publishing
- `ssh` client access for ASUS router publishing
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
- `MQTT_TOPIC`, optional state-topic override for publishers with one state topic

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

`--force-copy` only replaces the installed app directory. If
`/etc/homelab-ha-discovery/host-metrics.json` already exists, `bootstrap` keeps
it unless `--force-config` is also passed:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc --force-copy --force-config
```

To regenerate only `host-metrics.json` without copying the app or rebuilding the
virtual environment, run detect with `--force`:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py detect --ha-device-id hpc --force
```

Both `--force-config` and `detect --force` replace the whole generated config,
so preserve any manual edits first.

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
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py logs --follow
python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py status
```

During `install`, if existing
`/etc/systemd/system/homelab-ha-discovery-*.service` files are present and stdin
is interactive, the installer prompts before removing them. Answering yes
removes those generated unit files before writing the units from the current
`host-metrics.json`; answering no keeps them. For scripted runs, pass
`--clean-existing-units` to remove them without prompting, or
`--no-clean-existing-units` to keep them without prompting. The cleanup only
removes matching unit files; it does not stop services or edit
`host-metrics.json`.

After units are installed, the installer can manage the generated services:

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py logs
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py logs --follow --lines 200 --since "1 hour ago"
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py restart
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py stop
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py disable --now
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py uninstall
```

`logs` reads the journal for the generated units. `restart`, `stop`, and
`disable` operate on the units described by the current `host-metrics.json`;
`disable --now` also stops them. `uninstall` scans for matching generated unit
files, stops and disables those units, removes only the generated
`homelab-ha-discovery-*.service` files, and reloads systemd. It leaves the app
directory, `host-metrics.json`, `mqtt.env`, MQTT retained discovery config, and
Home Assistant entities untouched.

Generated units use `EnvironmentFile=-/etc/homelab-ha-discovery/mqtt.env`, but
`enable --now` refuses to enable/start services when the real env file is
missing unless `--allow-missing-mqtt-env` is passed. The units run the existing
publishers in long-running `--timer` mode. Default intervals are CPU and GPU
`5.0` seconds, disk and NVMe SMART `60.0` seconds, network `1.0`
second, Docker containers `60.0` seconds, ASUS router CPU `1.0` second, ASUS
router network `1.0` second, and ASUS router connected clients `1.0` second.
Generated `host-metrics.json` also includes a top-level
`timer_publish_discovery_config` default of `60.0`, so generated services
republish retained Home Assistant discovery config every 60 seconds. Set it to
`null` to disable that globally, or add `timer_publish_discovery_config` to an
individual service entry to override it for that service.

Detect/bootstrap also adds a disabled Docker container template entry:

```json
{
  "type": "docker_containers",
  "enabled": false,
  "timer": 60.0,
  "include_label": "homelab-ha-discovery.enabled=true",
  "expire_after": null,
  "missing_requirements": [],
  "note": "disabled template; enable manually after confirming Docker socket access"
}
```

The Docker entry uses label filtering by default so Home Assistant does not fill
with temporary or internal containers. Remove `include_label` to publish all
currently running containers, add `"all": true` to include stopped containers,
add `docker_command` to use a non-default Docker CLI path, or add
`"debug": true` to print Docker publisher progress into the service journal.
The generated `"expire_after": null` keeps the timer-mode default of three
times the service timer; set `"expire_after": 0` to disable expiry, or set
another non-negative seconds value to override it.
The service user must be able to read Docker state. Membership in the `docker`
group is common, but Docker socket access is effectively root-equivalent and
should be treated carefully.

Detect/bootstrap also adds disabled ASUS router template entries without probing
the router over SSH:

```json
[
  {
    "type": "asus_router_cpu",
    "enabled": false,
    "timer": 1.0,
    "router_name": "ASUS AX86U",
    "ssh_user": "router-user",
    "ssh_ip": "router-ip-address",
    "ssh_port": 22,
    "note": "disabled template; edit SSH settings and enable manually"
  },
  {
    "type": "asus_router_connected_clients",
    "enabled": false,
    "timer": 1.0,
    "router_name": "ASUS AX86U",
    "ssh_user": "router-user",
    "ssh_ip": "router-ip-address",
    "ssh_port": 22,
    "note": "disabled template; edit SSH settings and enable manually"
  },
  {
    "type": "asus_router_network",
    "enabled": false,
    "timer": 1.0,
    "router_name": "ASUS AX86U",
    "dev": "eth0",
    "ssh_user": "router-user",
    "ssh_ip": "router-ip-address",
    "ssh_port": 22,
    "note": "disabled template; edit SSH settings and enable manually"
  }
]
```

Edit those entries before enabling them. Add more ASUS router entries to monitor
multiple routers; keep each `router_name` stable because it is used in generated
service names, MQTT topics, and Home Assistant unique IDs. Connected-client
entries may include `client_list_command` to override the default remote
command. Router network entries use the `router_name` and `dev` combination in
generated unit names, so multiple interfaces on one router stay separate.
Router network entries may include `network_command` to override the default
remote `/proc/net/dev` sampler.

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
throughput state. Speeds are published in `Mbps`, where `Mbps` means megabits
per second using 1,000,000 bits per second. Values are rounded to three decimal
places; `0.001` means 1 Kbps and `1.000` means 1 Mbps.

Docker container metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc
```

The Docker container publisher runs local Docker CLI commands and dynamically
enumerates currently running containers on each run. It publishes one Home
Assistant discovery set and one state payload per included container, for
example separate `plex`, `gitlab`, and `nginx` payloads. The container component
is derived from the `homelab-ha-discovery.component` label when present,
otherwise from the container name. Do not use container IDs as stable Home
Assistant identity because they change when containers are recreated. If two
containers resolve to the same component, the script exits before publishing.
Discovery and state messages are batched through one MQTT connection per
publish cycle.

Recommended production mode is Docker label filtering:

```bash
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true
```

`homelab-ha-discovery.enabled` is treated as a boolean opt-in label. Passing
`--include-label homelab-ha-discovery.enabled` is equivalent to
`--include-label homelab-ha-discovery.enabled=true`. Containers with
`homelab-ha-discovery.enabled=false` are excluded, and passing
`--include-label homelab-ha-discovery.enabled=false` exits with an error.

Use `--all` to include stopped containers as well as running containers, and
`--docker-command` to use a non-default Docker CLI path. Network speeds are
computed from two `docker stats` samples and published in `Mbps`, where `Mbps`
means megabits per second using 1,000,000 bits per second. Values are rounded
to three decimal places. Docker network counter resets, such as after a
container restart, report `0.0` speed for that interval.

In timer mode, Docker discovery config sets `expire_after` to three times the
timer by default, so Home Assistant marks stale container sensors unavailable
after missed updates. For example, `--timer 60` defaults to `expire_after=180`.
Use `--expire-after 0` for never expire, or pass another seconds value:

```bash
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0 --expire-after 0
```

Add `--debug` when troubleshooting. This prints timestamped sample counts,
included containers, timer sleeps, discovery decisions, state topics, and
payloads to stderr:

```bash
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0 --timer-publish-discovery-config 60.0 --debug
```

ASUS router CPU metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address
```

The ASUS router CPU publisher runs `top -bn1` and
`cat /sys/class/thermal/thermal_zone*/temp` remotely over SSH. `--ssh-port`
defaults to `22`. `--ha-device-id` remains the Home Assistant/MQTT device
identity; `--router-name` is normalized into the router component, for example
`asus_ax86u` for `ASUS AX86U`. Temperature output is treated as millidegrees
Celsius, and the highest valid thermal zone value is published. Each remote SSH
command has a 10-second timeout. If a router needs different commands, override
them with `--top-command` or `--temperature-command`; generated systemd config
entries may also include `top_command` and `temperature_command`.

ASUS router network metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22
```

The ASUS router network publisher generates a remote `/proc/net/dev` sampler
for `--dev`, reads RX/TX bytes twice one second apart over SSH, validates that
counters are present and non-decreasing, and publishes download/upload speeds
in `Mbps`. `--ssh-port` defaults to `22`. `--ha-device-id` remains the Home
Assistant/MQTT device identity; `--router-name` is normalized into the router
component, for example `asus_ax86u` for `ASUS AX86U`; `--dev` is the router
interface component, for example `eth0`. If a router needs a different command,
override it with `--network-command`; generated systemd config entries may also
include `network_command`.

ASUS router connected-client metrics:

```bash
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22
```

The ASUS router connected-client publisher runs
`cat /var/lib/misc/dnsmasq.leases; echo "---END_LEASES---"; cat /tmp/clientlist.json`
remotely over SSH. It recurses through nested `clientlist.json` objects, so
top-level wrappers such as an AP MAC key are fine. It publishes every MAC found
under ASUS interface sections such as `2G`, `5G`, and `wired_mac`; DHCP-only
lease rows that are absent from `clientlist.json` are not included. MAC
addresses are normalized to uppercase. DHCP hostnames are matched by MAC first,
then IP as a fallback. Missing DHCP hostnames are published as `" - "`, and
missing RSSI values, such as wired clients, are published as `"N/A"`. If a
router needs a different command, override it with `--client-list-command`;
generated systemd config entries may also include `client_list_command`.

For manual troubleshooting, add `--debug` to print progress messages to stderr.
For connected-client runs, debug output also includes the raw SSH output
between begin/end markers, plus dnsmasq lease counts, `clientlist.json`
top-level keys, matched interface sections, MAC counts, and sample extracted
clients:

```bash
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22 --timer 1.0 --timer-publish-discovery-config 60.0 --debug
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22 --timer 1.0 --timer-publish-discovery-config 60.0 --debug
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22 --timer 1.0 --timer-publish-discovery-config 60.0 --debug
```

For frequent systemd timer runs, use `--publisher-only` after a normal run has registered discovery config:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --publisher-only
```

For long-running service mode, use `--timer SECONDS`. Most publishers publish
the first metric immediately, then sleep between publish attempts. Local
network metrics establish a baseline first, wait one interval, then publish the
first calculated speed. Docker container metrics also establish a baseline
first and re-enumerate containers every interval. ASUS router network metrics
perform their one-second remote sample during each publish attempt:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --timer 1.0
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --timer 1.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0
```

Without `--publisher-only`, `--timer` publishes discovery config once at
startup, then publishes only metric state each interval. For local network and
Docker container metrics, the startup discovery config is published before the
first calculated metric state after the baseline interval. Newly included
Docker containers publish discovery config on the next timer interval and
metric state after they have a previous network sample. With
`--timer --publisher-only`, it publishes only metric state each interval.

To republish retained discovery config periodically during long-running service mode, add `--timer-publish-discovery-config SECONDS`:

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --timer 1.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --timer 1.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0 --timer-publish-discovery-config 60.0
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

With `--ha-device-id hpc --router-name "ASUS AX86U"`, ASUS router CPU metrics
publish state to:

```text
homelab-ha-discovery/asus_ax86u/cpu/metrics/hpc
```

Payload:

```json
{"CPU Usages":37.8,"Temperature":54.0}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_cpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_cpu_temperature/config
```

The Home Assistant sensor names also use the router name, for example
`hpc ASUS AX86U CPU Usage`. Because the normalized router name is included in
Home Assistant unique IDs, changing `--router-name` changes the entities.

With `--ha-device-id hpc --router-name "ASUS AX86U" --dev eth0`, ASUS router
network metrics publish state to:

```text
homelab-ha-discovery/asus_ax86u/eth0/metrics/hpc
```

Payload:

```json
{"Download Speed":0.001,"Upload Speed":1.0}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_eth0_download_speed/config
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_eth0_upload_speed/config
```

The Home Assistant sensor names include the router name and interface, for
example `hpc ASUS AX86U eth0 Download Speed`. Because the normalized router
name and interface are included in Home Assistant unique IDs, changing either
`--router-name` or `--dev` changes the entities.

With `--ha-device-id hpc --router-name "ASUS AX86U"`, ASUS router
connected-client metrics publish state to:

```text
homelab-ha-discovery/asus_ax86u/connected_clients/metrics/hpc
```

Payload:

```json
[{"mac":"8C:FD:49:49:7B:58","ip":"192.168.4.72","rssi":"-68","interface":"2G","name":"mushroom_02_pc0"}]
```

Discovery topic:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_connected_clients/config
```

Home Assistant discovery creates one count sensor named like
`hpc ASUS AX86U Connected Clients`; its value template reads the array length
with `{{ value_json | count }}`. The detailed client list remains in the MQTT
state payload.

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
{"Download Speed":0.001,"Upload Speed":1.0}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_ppp0_download_speed/config
homeassistant/sensor/homelab_ha_discovery_hpc_ppp0_upload_speed/config
```

Network speed sensors use `Mbps`, where `Mbps` means megabits per second using
1,000,000 bits per second. Values are rounded to three decimal places; `0.001`
means 1 Kbps and `1.000` means 1 Mbps. The Home Assistant sensor names also
use the network interface component, for example `hpc ppp0 Download Speed`.
Because the interface component is included in Home Assistant unique IDs,
changing `--dev` changes the entities.

With `--ha-device-id hpc`, Docker container metrics publish one state topic per
included container. For a container named `plex`, the state topic is:

```text
homelab-ha-discovery/hpc/docker/plex/metrics
```

Payload:

```json
{"State":"running","Health":"healthy","Restart Count":2,"CPU Usage":2.318,"Memory Usage MB":512.4,"Memory Limit MB":8192.0,"Memory Usage Percent":6.25,"Download Speed":0.001,"Upload Speed":1.0}
```

Discovery topics:

```text
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_state/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_health/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_restart_count/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_cpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_memory_usage_mb/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_memory_limit_mb/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_memory_usage_percent/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_download_speed/config
homeassistant/sensor/homelab_ha_discovery_hpc_docker_plex_upload_speed/config
```

If `plex`, `gitlab`, and `nginx` are included, each container gets its own
state topic and discovery topics. Removed or renamed containers are not
automatically deleted from Home Assistant; old retained discovery config should
be cleaned up manually only when intended.

If `MQTT_TOPIC` is set, publishers with one state topic use it as the state
topic and discovery config points to that exact topic. Docker container metrics
always use per-container state topics.

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
python3 -m py_compile src/homelab_ha_discovery/collectors/docker_containers.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py
python3 -m py_compile src/homelab_ha_discovery/collectors/router_asus_ssh.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/install_debian_host_systemd.py
python3 -m unittest discover -s tests
```

Run `pytest` too if it is available.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
