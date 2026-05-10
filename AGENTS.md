# AGENTS.md

## Purposes
1. Use shared Python modules for reusable MQTT publishing, environment loading, Home Assistant discovery, and common parsing helpers.
1. Keep metric collection and parsing code separated by sensor type when command output or payload fields differ.
1. Keep ASUS router collectors are collected remotely over SSH and may use different CLI commands.

## Folder Layout
.
├── AGENTS.md
├── README.md
├── README.zh-tw.md
└── src
    ├── homelab_ha_discovery
    │   ├── collectors
    │   └── scripts
- Device identity is runtime data, not a folder split. Shared scripts should accept a device value and use it for MQTT topics, Home Assistant unique IDs, and device identifiers.
- Python 3 code for Debian homelab hosts runs on the host itself, usually via a systemd timer.
- Python 3 code for ASUS router collectors runs on a Debian homelab host and collects router data via SSH remote commands. The user will provide the required router CLI commands.
- Each Python 3 script runs independently. The rough code flow is:
  - `src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id <device>` -> parse CPU usage from the `top` CLI tool and CPU temperature from the `sensors` CLI tool -> publish the data to the MQTT server.
  - `src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id <device> --dev <path>` -> run `sudo smartctl -a <path>` locally, parse disk SMART attributes, derive the disk component from the device path basename such as `sda` for `/dev/sda` -> publish the data to the MQTT server.
  - `src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id <device> --dev <path>` -> run `sudo smartctl -a <path>` locally, parse NVMe SMART fields, derive the NVMe component from the device path basename such as `nvme0` for `/dev/nvme0` -> publish the data to the MQTT server.
  - `src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id <device> --dev <interface>` -> read Linux interface byte counters with `psutil.net_io_counters(pernic=True)`, compute download/upload speed from two samples, use the interface name as the MQTT/Home Assistant component, and publish the data to the MQTT server.
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
- Scripts that support `--timer SECONDS` run as long-running publishers: publish immediately, then repeat every positive `SECONDS`, unless the metric requires a baseline sample such as network throughput.
- For `--timer` runs without `--publisher-only`, publish discovery config once at startup, then publish metric state each interval. For baseline-sampled metrics, publish discovery config before the first calculated metric state. For `--timer --publisher-only`, publish only metric state each interval.
- Scripts may support `--timer-publish-discovery-config SECONDS` with `--timer` to republish retained discovery config periodically. Without this option, keep the discovery-once timer behavior. Do not combine it with `--publisher-only`.
- Discovery config publishes should use `publish_mqtt(..., retain=True)`.
- Metric state publishes should remain non-retained by default.
- Discovery config must point to the exact state topic used by the metric publish, including any supported topic override.
- CPU metrics publish state to `<prefix>/cpu/metrics/<device>` with payload `{"CPU Usages":<percent>,"Temperature":<celsius>}`. Discovery topics are `homeassistant/sensor/homelab_ha_discovery_<device>_cpu_usage/config` and `homeassistant/sensor/homelab_ha_discovery_<device>_cpu_temperature/config`.
- GPU metrics publish one nested state payload. When `--gpu` is omitted, publish all detected GPUs in `nvidia-smi` row order to `<prefix>/gpu/usages/<device>` as `gpu0`, `gpu1`, and so on. Each GPU object includes `GPU Card Name`, `GPU Usages`, `Memory Usage`, and `Temperature`.
- When GPU metrics use `--gpu INDEX`, publish only `gpu<INDEX>` to `<prefix>/gpu/usages/<device>/gpu<INDEX>`. If `INDEX` is out of range, exit with an error before publishing discovery config or state.
- GPU discovery should expose separate sensors for every included GPU metric, for example `homeassistant/sensor/homelab_ha_discovery_<device>_gpu0_usage/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_gpu0_memory_usage/config`, and `homeassistant/sensor/homelab_ha_discovery_<device>_gpu0_temperature/config`. Discovery value templates should read from the nested GPU object, for example `{{ value_json['gpu0']['GPU Usages'] }}`. Do not create a sensor for `GPU Card Name`; it is payload metadata only.
- Disk SMART metrics run `sudo smartctl -a <dev>` locally with `LC_ALL=C`, parse SMART attribute IDs `9`, `194`, `5`, and `197`, and publish state to `<prefix>/<disk>/metrics/<device>` with payload `{"Power On Hours":<hours>,"Temperature":<celsius>,"Reallocated Sectors":<count>,"Pending Sectors":<count>}`. The `<disk>` component is the normalized basename of `--dev`, for example `sda` for `/dev/sda`. If any required SMART metric is missing or unparsable, exit with an error before publishing discovery config or state.
- Disk SMART discovery topics include the disk component, for example `homeassistant/sensor/homelab_ha_discovery_<device>_sda_power_on_hours/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_sda_temperature/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_sda_reallocated_sectors/config`, and `homeassistant/sensor/homelab_ha_discovery_<device>_sda_pending_sectors/config` for `--dev /dev/sda`. Discovery value templates should read from the shared JSON payload. The disk component is included in Home Assistant unique IDs so multiple disks on one device can be monitored separately.
- NVMe SMART metrics run `sudo smartctl -a <dev>` locally with `LC_ALL=C`, parse `Critical Warning`, `Media and Data Integrity Errors`, `Available Spare`, `Percentage Used`, `Critical Comp. Temperature Time`, `Temperature`, `Data Units Written`, and `Power On Hours`, and publish state to `<prefix>/<nvme>/metrics/<device>` with payload `{"Critical Warning":<integer>,"Media and Data Integrity Errors":<count>,"Available Spare":<percent>,"Percentage Used":<percent>,"Critical Temperature Time":<minutes>,"temperature_c":<celsius>,"data_written_tb":<tb>,"power_on_hours":<hours>}`. The `<nvme>` component is the normalized basename of `--dev`, for example `nvme0` for `/dev/nvme0`. If any required NVMe SMART metric is missing or unparsable, exit with an error before publishing discovery config or state. Run one process or service per NVMe controller.
- NVMe SMART discovery topics include the NVMe component, for example `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_critical_warning/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_media_data_integrity_errors/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_available_spare/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_percentage_used/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_critical_temperature_time/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_temperature_c/config`, `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_data_written_tb/config`, and `homeassistant/sensor/homelab_ha_discovery_<device>_nvme0_power_on_hours/config` for `--dev /dev/nvme0`. Discovery value templates should read from the shared JSON payload. The NVMe component is included in Home Assistant unique IDs so multiple NVMe controllers on one device can be monitored separately.
- Network metrics read local Linux byte counters with `psutil.net_io_counters(pernic=True)`, require `--dev` to match a network interface key such as `ppp0`, and publish state to `<prefix>/<interface>/metrics/<device>` with payload `{"Download Speed":<kb_per_second>,"Upload Speed":<kb_per_second>}`. `KB/s` means 1024 bytes per second, and values are rounded to two decimal places. If the interface is missing, elapsed sample time is invalid, or counters decrease unexpectedly, exit with an error before publishing discovery config or state.
- Network discovery topics include the interface component, for example `homeassistant/sensor/homelab_ha_discovery_<device>_ppp0_download_speed/config` and `homeassistant/sensor/homelab_ha_discovery_<device>_ppp0_upload_speed/config` for `--dev ppp0`. Discovery value templates should read from the shared JSON payload.
- Network timer runs establish a baseline sample first, wait one timer interval, then publish the first calculated speed. Subsequent intervals calculate speed from the previous sample to the current sample. With `--timer-publish-discovery-config`, republish retained discovery config before that interval's metric state.

## Home Assistant cleanup
This project was renamed from `homelab-mqtt-monitor` to `homelab-ha-discovery`.
Old Home Assistant entities or retained discovery configs using `homelab-mqtt-monitor` may need manual cleanup.
Do not publish deletion payloads to the MQTT broker unless the user explicitly asks for a cleanup operation.

## Command safety
- You may run localhost health checks and project tests.
- Ask before destructive commands such as deleting files, changing git history, or stopping containers.
- Prefer minimal validation commands first.
- Do not run `sudo smartctl` against real disks unless the user explicitly asks.
- Do not run SSH commands against routers or homelab servers unless the user explicitly asks.
- Do not publish test MQTT messages to the real broker unless the user explicitly asks.
- Prefer parsing saved sample command output locally when possible.

## Rules
- Follow the existing structure and style.
- Prefer small diffs.
- Do not add dependencies without asking.
- Do not rename or move files unless necessary.
- Do not update `requirements.txt` unless explicitly asked.
- Keep changes scoped to the requested script.
- Every code change must include a documentation check for `AGENTS.md`, `README.md`, and `README.zh-tw.md`; update all affected docs in the same change when behavior, commands, topics, environment variables, setup, validation, or user-facing usage changes.
- Keep `README.md` English-only except for language selector link labels.
- Keep `README.zh-tw.md` as the Traditional Chinese counterpart to `README.md`; when `README.md` changes, update `README.zh-tw.md` with corresponding content in the same change.
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
