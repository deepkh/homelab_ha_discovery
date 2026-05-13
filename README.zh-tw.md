# homelab-ha-discovery

自動將 homelab 基礎設施的監控資料，發布成 Home Assistant MQTT entities。

這個專案會收集 Debian 主機、Docker container、Frigate、NVIDIA GPU、
SMART 硬碟/NVMe、Linux network interface、ASUS router 等資料，並透過 MQTT
發布 Home Assistant discovery config 與 state。

## 為什麼需要這個專案？

Home Assistant 可以監控 homelab infrastructure，但如果每一個 MQTT discovery
payload 都手寫，會非常重複且容易出錯。

`homelab-ha-discovery` 提供一組小型 Python publisher：

- 收集 homelab metrics
- 自動產生穩定的 Home Assistant MQTT discovery entities
- 發布 metric state 到 MQTT
- 讓 Home Assistant 自動出現 sensor

## 簡單流程

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

## 支援的監控項目

| 類型 | 範例 |
|---|---|
| CPU | 使用率、溫度 |
| NVIDIA GPU | 使用率、記憶體使用率、溫度 |
| Disk SMART | power-on hours、temperature、reallocated/pending sectors |
| NVMe SMART | warning、spare、percentage used、temperature、written TB |
| Network | download/upload speed |
| Docker | state、health、restart count、CPU、memory、network |
| Frigate | system、camera、detector、GPU、storage metrics |
| ASUS router | CPU、temperature、network speed、connected clients |

## 需求

- Python 3.10+
- Home Assistant 可以連線的 MQTT broker
- Home Assistant 已啟用 MQTT integration
- 多數 local collector 需要 Linux host
- 選配：Docker、Frigate、NVIDIA tools、smartmontools、ASUS router SSH access

## 快速開始

Clone 專案：

```bash
git clone https://github.com/deepkh/homelab_ha_discovery.git
cd homelab_ha_discovery
```

建立 Python environment：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

建立 MQTT 設定：

```bash
sudo mkdir -p /etc/homelab-ha-discovery
sudo editor /etc/homelab-ha-discovery/mqtt.env
```

範例：

```bash
HA_MQTT_HOST=192.168.4.27
HA_MQTT_PORT=1883
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
HA_MQTT_USERNAME=your-user
HA_MQTT_PASSWORD=your-password
```

手動執行一個 publisher：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc
```

## 建議的 systemd 安裝方式

產生設定檔：

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc
```

編輯設定：

```bash
sudo editor /etc/homelab-ha-discovery/mqtt.env
sudo editor /etc/homelab-ha-discovery/host-metrics.json
```

從 `/opt/homelab-ha-discovery` 的 managed copy 安裝 systemd services：

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py install
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py enable --now
```

檢查 logs：

```bash
journalctl -u 'homelab-ha-discovery-*' -f
```

## 文件

README 只保留簡單入口，詳細內容放在 `docs/`。

- [Systemd install](docs/install-systemd.md)
- [Configuration](docs/configuration.md)
- [Publishers](docs/publishers.md)
- [MQTT topics](docs/mqtt-topics.md)
- [Home Assistant](docs/home-assistant.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Development](docs/development.md)

## Development

快速語法檢查：

```bash
python3 -m py_compile src/homelab_ha_discovery/**/*.py
```

如果有 tests：

```bash
pytest
```

## License

MIT
