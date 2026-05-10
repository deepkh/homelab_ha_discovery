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
- 用於 CPU 指標發布的 `top` 和 `sensors`。在 Debian 上，`sensors` 由 `lm-sensors` 提供。
- 用於 NVIDIA GPU 發布的 `nvidia-smi`
- 用於磁碟與 NVMe SMART 發布的 `smartctl`。在 Debian 上，`smartctl` 由 `smartmontools` 提供。
- MQTT broker 存取權限

## 安裝設定

這些指示提供給人工操作人員使用。

### 安裝 Python 3

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl ca-certificates
```

### 建立 Python 3 虛擬環境

只有在 `.venv/` 不存在或是空的時候，才建立虛擬環境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 將 Python 3 所需套件安裝到 `.venv`（選用）

```bash
pip install paho-mqtt
```

### 從 `requirements.txt` 安裝所需套件

```bash
pip install -r requirements.txt
```

### 將 `.venv/` 已安裝套件匯出到 `requirements.txt`

```bash
pip freeze > requirements.txt
```

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

CPU 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc
```

NVIDIA GPU 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc
```

未指定 `--gpu` 時，會依照 `nvidia-smi` 的列順序將所有偵測到的 NVIDIA
GPU 發布為 `gpu0`、`gpu1`，以此類推。若只要發布單一 GPU，請傳入其從
0 開始的 index：

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --gpu 0
```

磁碟 SMART 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda
```

磁碟 SMART 發布器會在本機執行 `sudo smartctl -a <dev>`。請在此 repository
外部設定 sudo，讓 service user 可以非互動式執行所需的 `smartctl` 指令。
MQTT 和 Home Assistant discovery 中的磁碟 component 會由 `--dev` 的 basename
產生，例如 `/dev/sda` 會使用 `sda`。

NVMe SMART 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0
```

NVMe SMART 發布器也會在本機執行 `sudo smartctl -a <dev>`。請為每個 NVMe
controller 執行一個 process 或 service，例如 `/dev/nvme0`、`/dev/nvme1`
等等。MQTT 和 Home Assistant discovery 中的 NVMe component 會由 `--dev`
的 basename 產生，例如 `/dev/nvme0` 會使用 `nvme0`。

若要頻繁透過 systemd timer 執行，請在一般執行已註冊 discovery config 後使用 `--publisher-only`：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0 --publisher-only
```

若要使用長時間執行的服務模式，請使用 `--timer SECONDS`。第一次指標發布會立即發生，之後腳本會在每次發布嘗試之間休眠：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0 --timer 5.0
```

未使用 `--publisher-only` 時，`--timer` 會在啟動時發布一次 discovery config，之後每個 interval 只發布 metric state。使用 `--timer --publisher-only` 時，每個 interval 只發布 metric state。

若要在長時間執行的服務模式中定期重新發布保留的 discovery config，請加入 `--timer-publish-discovery-config SECONDS`：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --device hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --device hpc --dev /dev/sda --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --device hpc --dev /dev/nvme0 --timer 5.0 --timer-publish-discovery-config 60.0
```

如果未設定 `--timer-publish-discovery-config`，timer 行為會維持只在啟動時發布一次 discovery。此選項需要 `--timer`，且不能與 `--publisher-only` 一起使用。

隱藏的 `--host` 參數可作為 `--device` 的相容性別名。

## MQTT Topics

使用預設 topic prefix 和 `--device hpc` 時，CPU 指標會將 state 發布到：

```text
homelab-ha-discovery/cpu/metrics/hpc
```

Payload：

```json
{"CPU Usages":37.8,"Temperature":54.0}
```

Discovery topics：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_cpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_cpu_temperature/config
```

未指定 `--gpu` 時，NVIDIA GPU 指標會將 state 發布到：

```text
homelab-ha-discovery/gpu/usages/hpc
```

Payload：

```json
{"gpu0":{"GPU Card Name":"NVIDIA GeForce RTX 5060 Ti","GPU Usages":55.2,"Memory Usage":41.7,"Temperature":72},"gpu1":{"GPU Card Name":"NVIDIA GeForce RTX 3060","GPU Usages":30.0,"Memory Usage":22.5,"Temperature":61},"gpu2":{"GPU Card Name":"NVIDIA RTX A4000","GPU Usages":80.4,"Memory Usage":70.1,"Temperature":68}}
```

使用 `--gpu 0` 時，NVIDIA GPU 指標只會將 `gpu0` 發布到：

```text
homelab-ha-discovery/gpu/usages/hpc/gpu0
```

Payload：

```json
{"gpu0":{"GPU Card Name":"NVIDIA GeForce RTX 5060 Ti","GPU Usages":55.2,"Memory Usage":41.7,"Temperature":72}}
```

每次執行會為該次包含的每張 GPU 發布 discovery topics：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_gpu0_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_gpu0_memory_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_gpu0_temperature/config
```

`GPU Card Name` 只會作為 payload metadata；不會為它建立 Home Assistant
sensor。

使用 `--dev /dev/sda` 時，磁碟 SMART 指標會將 state 發布到：

```text
homelab-ha-discovery/sda/metrics/hpc
```

Payload：

```json
{"Power On Hours":3103,"Temperature":42,"Reallocated Sectors":0,"Pending Sectors":0}
```

Discovery topics：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_sda_power_on_hours/config
homeassistant/sensor/homelab_ha_discovery_hpc_sda_temperature/config
homeassistant/sensor/homelab_ha_discovery_hpc_sda_reallocated_sectors/config
homeassistant/sensor/homelab_ha_discovery_hpc_sda_pending_sectors/config
```

Home Assistant sensor 名稱也會使用磁碟 component，例如 `hpc sda Power On
Hours`。因為磁碟 component 會包含在 Home Assistant unique ID 中，變更
`--dev` 會改變 entities。

使用 `--dev /dev/nvme0` 時，NVMe SMART 指標會將 state 發布到：

```text
homelab-ha-discovery/nvme0/metrics/hpc
```

Payload：

```json
{"Critical Warning":0,"Media and Data Integrity Errors":0,"Available Spare":100,"Percentage Used":3,"Critical Temperature Time":0,"temperature_c":35,"data_written_tb":5.06,"power_on_hours":6528}
```

Discovery topics：

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

Home Assistant sensor 名稱也會使用 NVMe component，例如 `hpc nvme0
Available Spare`。因為 NVMe component 會包含在 Home Assistant unique ID
中，請為每個 controller 執行一個 publisher，以保持 entities 穩定。
`Available Spare` 和 `Percentage Used` 使用 `%`；`Critical Temperature Time`
使用 `min`；`temperature_c` 使用 `°C`；`power_on_hours` 使用 `h`；
`data_written_tb` 使用 `TB`；warning 和 error 指標沒有單位。

如果設定了 `MQTT_TOPIC`，發布器會將它作為 state topic，且 discovery config
會指向同一個 topic。

Discovery config 會被 retain。Metric state 預設不 retain。

## 開發

Collectors 位於 `src/homelab_ha_discovery/collectors/`；可執行腳本位於 `src/homelab_ha_discovery/scripts/`。

相關驗證指令：

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

如果有測試，請執行 `pytest`。

## 授權

此專案採用 MIT License 授權。請見 [LICENSE](LICENSE)。
