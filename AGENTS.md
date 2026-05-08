# AGENTS.md

## Purposes
1. Use shared Python modules for reusable metric collection, parsing, MQTT publishing, and Home Assistant discovery.
1. Routers should stay separate from Debian hosts because they are collected remotely over SSH and will have different command behavior.

## Folder Layout
.
├── AGENTS.md
└── src
    ├── homelab_monitor
    │   ├── collectors
    │   └── scripts
    └── network
        ├── ax86u
        └── ax86upro
- Host identity is runtime data, not a folder split. Shared scripts should accept a host value and use it for MQTT topics, Home Assistant unique IDs, and device identifiers.
- Python 3 code for Debian homelab hosts runs on the host itself, usually via a systemd timer.
- Python 3 code for ASUS router collectors runs on a Debian homelab host and collects router data via SSH remote commands. The user will provide the required router CLI commands.
- Each Python 3 script runs independently. The rough code flow is:
  - `src/homelab_monitor/scripts/publish_cpu_usage.py --host <host>` -> parse CPU usage from the `top` CLI tool -> publish the data to the MQTT server.
- MQTT payloads and discovery configuration should follow Home Assistant-compatible formats.
- Debian homelab hosts run Debian 13 on x86_64.
- ASUS routers are ASUS WiFi routers.
 
## Local services
MQTT server: `mqtt.netsync.tv:1833`.

Recommended environment variables:
- `HA_MQTT_HOST=mqtt.netsync.tv`
- `HA_MQTT_PORT=1833`
- `HA_MQTT_TOPIC_PREFIX=homelab-mqtt-monitor`
- `HA_MQTT_USERNAME=...`
- `HA_MQTT_PASSWORD=...`

Use command `export $(grep -v '^#'  /etc/homelab-mqtt-monitor/mqtt.env | xargs)` to export they.

Do not store MQTT credentials in this repository. For systemd services or timers, prefer an environment file outside the repo, for example `/etc/homelab-mqtt-monitor/mqtt.env`, referenced by service files with `EnvironmentFile=/etc/homelab-mqtt-monitor/mqtt.env`. The file should be readable only by the service user or root.

Suggested MQTT/Home Assistant conventions:
- Use stable `unique_id` values based on host, component, and metric name.
- Use `HA_MQTT_TOPIC_PREFIX` for the root topic prefix, defaulting to `homelab-mqtt-monitor`.
- Use predictable state topics, for example `<prefix>/<host>/<component>/<metric>/state`.
- Use predictable discovery topics, for example `homeassistant/sensor/<host>_<component>_<metric>/config`.
- Publish Home Assistant discovery config when the script starts unless the existing script uses another pattern.
- Keep device names and identifiers stable so Home Assistant does not create duplicate entities.

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
- Add shared helpers only when the user asks or when existing duplicated logic makes the change clearly safer.
- Do not introduce host-specific folders for Debian homelab hosts; pass host identity as runtime data.

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
