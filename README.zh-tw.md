# homelab-ha-discovery

![Python](https://img.shields.io/badge/Python-3-blue?logo=python)
![MQTT](https://img.shields.io/badge/MQTT-publisher-660066?logo=mqtt)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-discovery-41BDF5?logo=homeassistant)
![Debian](https://img.shields.io/badge/Debian-13-A81D33?logo=debian)
![License](https://img.shields.io/badge/License-MIT-green)

[English](README.md) | [繁體中文](README.zh-tw.md)

用於 homelab 指標的 Python MQTT 發布器，支援 Home Assistant MQTT discovery。

目前可執行的發布器會從本機 Debian 主機收集指標，並將 JSON payload 發布到 MQTT。一般執行會先發布保留的 Home Assistant discovery config，然後發布目前的指標狀態。外部 systemd timer 執行可在 discovery 已註冊後使用 `--publisher-only`。也可以使用 `--timer SECONDS` 進入長時間執行的服務模式。

AI agent 和 repository 維護規則請見 [AGENTS.md](AGENTS.md)。

## 需求

- Python 3 執行環境
- 從 `requirements.txt` 安裝的 `paho-mqtt`
- 用於 CPU 使用率發布的 `top`
- 用於 NVIDIA GPU 發布的 `nvidia-smi`
- MQTT broker 存取權限

## 設定

腳本會從環境變數讀取 MQTT 設定，也會嘗試載入 `/etc/homelab-ha-discovery/mqtt.env`。

支援的環境變數：

- `HA_MQTT_HOST`，預設 `mqtt-server-ip`
- `HA_MQTT_PORT`，預設 `1833`
- `HA_MQTT_TOPIC_PREFIX`，預設 `homelab-ha-discovery`
- `HA_MQTT_USERNAME`，選用 MQTT username
- `HA_MQTT_PASSWORD`，選用 MQTT password
- `HA_MQTT_CLIENT_ID`，選用 MQTT client ID
- `MQTT_TOPIC`，選用 state topic 覆寫

不要將 MQTT 憑證存放在此 repository 中。對 systemd service 或 timer，請優先使用 repository 外部的環境檔，例如 `/etc/homelab-ha-discovery/mqtt.env`，並且只允許 service user 或 root 讀取。

環境檔範例：

```bash
HA_MQTT_HOST=mqtt-server-ip
HA_MQTT_PORT=1833
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
HA_MQTT_USERNAME=your-user
HA_MQTT_PASSWORD=your-password
```

## 使用方式

請從 repository root 執行。

CPU 使用率：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc
```

NVIDIA GPU 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc
```

若要頻繁透過 systemd timer 執行，請在一般執行已註冊 discovery config 後使用 `--publisher-only`：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --publisher-only
```

若要使用長時間執行的服務模式，請使用 `--timer SECONDS`。第一次指標發布會立即發生，之後腳本會在每次發布嘗試之間休眠：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0
```

未使用 `--publisher-only` 時，`--timer` 會在啟動時發布一次 discovery config，之後每個 interval 只發布 metric state。使用 `--timer --publisher-only` 時，每個 interval 只發布 metric state。

若要在長時間執行的服務模式中定期重新發布保留的 discovery config，請加入 `--timer-publish-discovery-config SECONDS`：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_usage.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
```

如果未設定 `--timer-publish-discovery-config`，timer 行為會維持只在啟動時發布一次 discovery。此選項需要 `--timer`，且不能與 `--publisher-only` 一起使用。

隱藏的 `--host` 參數可作為 `--device` 的相容性別名。

## MQTT Topics

使用預設 topic prefix 和 `--device hpc` 時，CPU 使用率會將 state 發布到：

```text
homelab-ha-discovery/cpu/usages/hpc
```

Payload：

```json
{"CPU Usages":37.8}
```

Discovery topic：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_cpu_usage/config
```

NVIDIA GPU 指標會將 state 發布到：

```text
homelab-ha-discovery/gpu/usages/hpc
```

Payload：

```json
{"GPU Usages":65.0,"Memory Usage":48.3}
```

Discovery topics：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_gpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_gpu_memory_usage/config
```

Discovery config 會被 retain。Metric state 預設不 retain。

## 開發

Collectors 位於 `src/homelab_ha_discovery/collectors/`；可執行腳本位於 `src/homelab_ha_discovery/scripts/`。

相關驗證指令：

```bash
python3 -m py_compile src/homelab_ha_discovery/mqtt.py
python3 -m py_compile src/homelab_ha_discovery/scripts/timer.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_cpu_usage.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_gpu_metrics.py
```

如果有測試，請執行 `pytest`。

## 授權

此專案採用 MIT License 授權。請見 [LICENSE](LICENSE)。
