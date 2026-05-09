# AGENTS.md

## Purposes
1. Use shared Python modules for reusable MQTT publishing, environment loading, Home Assistant discovery, and common parsing helpers.
1. Keep metric collection and parsing code separated by sensor type when command output or payload fields differ.
1. Keep ASUS router collectors are collected remotely over SSH and may use different CLI commands.

## Folder Layout
.
├── AGENTS.md
├── README.md
└── src
    ├── homelab_ha_discovery
    │   ├── collectors
    │   └── scripts
- Device identity is runtime data, not a folder split. Shared scripts should accept a device value and use it for MQTT topics, Home Assistant unique IDs, and device identifiers.
- Python 3 code for Debian homelab hosts runs on the host itself, usually via a systemd timer.
- Python 3 code for ASUS router collectors runs on a Debian homelab host and collects router data via SSH remote commands. The user will provide the required router CLI commands.
- Each Python 3 script runs independently. The rough code flow is:
  - `src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device <device>` -> parse CPU usage from the `top` CLI tool -> publish the data to the MQTT server.
- MQTT payloads and discovery configuration should follow Home Assistant-compatible formats.
- Debian homelab hosts run Debian 13 on x86_64.
- ASUS routers are ASUS WiFi routers.
 
## Local services
MQTT server: `mqtt-server-ip:1833`.

Recommended environment variables:
- `HA_MQTT_HOST=mqtt-server-ip`
- `HA_MQTT_PORT=1833`
- `HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery`
- `HA_MQTT_USERNAME=...`
- `HA_MQTT_PASSWORD=...`

For human operators, environment variables can be loaded from `/etc/homelab-ha-discovery/mqtt.env`. AI agents must not export credentials or run setup commands unless explicitly asked.

Do not store MQTT credentials in this repository. For systemd services or timers, prefer an environment file outside the repo, for example `/etc/homelab-ha-discovery/mqtt.env`, referenced by service files with `EnvironmentFile=/etc/homelab-ha-discovery/mqtt.env`. The file should be readable only by the service user or root.

Required MQTT/Home Assistant conventions:
- Use stable `unique_id` values based on device, component, and metric name.
- Use `HA_MQTT_TOPIC_PREFIX` for the root topic prefix, defaulting to `homelab-ha-discovery`.
- Use predictable state topics, for example `<prefix>/<device>/<component>/<metric>/state`.
- Use predictable discovery topics, for example `homeassistant/sensor/homelab_ha_discovery_<device>_<component>_<metric>/config`.
- Publish Home Assistant discovery config when the script supports discovery, unless the existing script uses another pattern.
- Keep device names and identifiers stable so Home Assistant does not create duplicate entities.

## Home Assistant auto-discovery
- Scripts that support Home Assistant MQTT discovery should publish retained discovery config on normal/manual runs, then publish the current metric state.
- Use `--publisher-only` for frequent systemd timer runs after discovery config has already been registered.
- Scripts that support `--timer SECONDS` run as long-running publishers: publish immediately, then repeat every positive `SECONDS`.
- For `--timer` runs without `--publisher-only`, publish discovery config once at startup, then publish metric state each interval. For `--timer --publisher-only`, publish only metric state each interval.
- Scripts may support `--timer-publish-discovery-config SECONDS` with `--timer` to republish retained discovery config periodically. Without this option, keep the discovery-once timer behavior. Do not combine it with `--publisher-only`.
- Discovery config publishes should use `publish_mqtt(..., retain=True)`.
- Metric state publishes should remain non-retained by default.
- Discovery config must point to the exact state topic used by the metric publish, including any supported topic override.
- CPU usage currently publishes state to `<prefix>/cpu/usages/<device>` with payload `{"CPU Usages":<percent>}` and discovery topic `homeassistant/sensor/homelab_ha_discovery_<device>_cpu_usage/config`.
- GPU metrics currently publish one state payload to `<prefix>/gpu/usages/<device>` with `GPU Usages` and `Memory Usage`; discovery should expose separate sensors for `gpu_usage` and `gpu_memory_usage` from that shared state topic.

## Home Assistant cleanup
This project was renamed from `homelab-mqtt-monitor` to `homelab-ha-discovery`.
Old Home Assistant entities or retained discovery configs using `homelab-mqtt-monitor` may need manual cleanup.
Do not publish deletion payloads to the MQTT broker unless the user explicitly asks for a cleanup operation.

## Command safety
- You may run localhost health checks and project tests.
- Ask before destructive commands such as deleting files, changing git history, or stopping containers.
- Prefer minimal validation commands first.
- Do not run SSH commands against routers or homelab servers unless the user explicitly asks.
- Do not publish test MQTT messages to the real broker unless the user explicitly asks.
- Prefer parsing saved sample command output locally when possible.

## Rules
- Every prompt usually affects only one Python 3 script.
- Follow the existing structure and style.
- Prefer small diffs.
- Do not add dependencies without asking.
- Do not rename or move files unless necessary.
- Do not update `requirements.txt` unless explicitly asked.
- Keep changes scoped to the requested script.
- Every code change must include a documentation check for `AGENTS.md` and `README.md`; update both in the same change when behavior, commands, topics, environment variables, setup, validation, or user-facing usage changes.
- If `README.md` is absent when a code change needs user-facing documentation, report that in the final response instead of silently leaving the documentation gap.
- Add shared helpers only when the user asks or when existing duplicated logic makes the change clearly safer.
- Do not introduce device-specific folders for Debian homelab hosts; pass device identity as runtime data.
- For router collectors, keep SSH connection hostnames separate from Home Assistant/MQTT device identity; use names such as `--ssh-host` or `--router-host` for connection targets.

## Validation
- Run only relevant tests.
- If available, run `pytest`, `ruff check .`, and `black --check .`.
- For a changed Python script, run `python3 -m py_compile path/to/script.py` when practical.
- If parser sample data exists, validate parsing against the sample data.
- Report exactly what was run.
- Do not assume validation tools exist unless they are already used in the repo.

## Output
- Summarize changes briefly.
- List changed files.
- Mention risks or unverified areas.

## Setup
AI agents must skip the `Setup` section. The instructions in the `Setup` section are only for human operators. Agents must not run setup or install commands unless the user explicitly asks.

### Install python3
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl ca-certificates
```

### Create python3 virtual environment
- Only if `.venv/` does not exist or is empty, create the virtual environment with:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install necessary libs to .venv for Python 3 (Optional)
```bash
pip install paho-mqtt
```

### Install necessary libs from requirements.txt
```bash
pip install -r requirements.txt
```

### Dump .venv/ installed libs to requirements.txt
```bash
pip freeze > requirements.txt
```
