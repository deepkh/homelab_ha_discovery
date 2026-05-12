# homelab-ha-discovery

![Python](https://img.shields.io/badge/Python-3-blue?logo=python)
![MQTT](https://img.shields.io/badge/MQTT-publisher-660066?logo=mqtt)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-discovery-41BDF5?logo=homeassistant)
![Debian](https://img.shields.io/badge/Debian-13-A81D33?logo=debian)
![License](https://img.shields.io/badge/License-MIT-green)

[English](README.md) | [繁體中文](README.zh-tw.md)

用於 homelab 指標的 Python MQTT 發布器，支援 Home Assistant MQTT discovery。

目前可執行的發布器會從本機 Debian 主機、本機 Docker containers、本機 Frigate instances，以及透過 SSH 從 ASUS routers 收集指標，並將 JSON payload 發布到 MQTT。一般執行會先發布保留的 Home Assistant discovery config，然後透過同一個 MQTT connection 發布目前 publish cycle 的指標狀態。外部 systemd timer 執行可在 discovery 已註冊後使用 `--publisher-only`。也可以使用 `--timer SECONDS` 進入長時間執行的服務模式。

AI agent 和 repository 維護規則請見 [AGENTS.md](AGENTS.md)。

## 需求

- Python 3 執行環境
- 從 `requirements.txt` 安裝的 `paho-mqtt`（MQTT 用）和 `psutil`（Linux network interface throughput 用）
- 用於 CPU 指標發布的 `top` 和 `sensors`。在 Debian 上，`sensors` 由 `lm-sensors` 提供。
- 用於 NVIDIA GPU 發布的 `nvidia-smi`
- 用於磁碟與 NVMe SMART 發布的 `smartctl`。在 Debian 上，`smartctl` 由 `smartmontools` 提供。
- Docker container 發布需要 Docker CLI 存取權限
- Frigate 發布需要能存取 `http://127.0.0.1:5000/api/metrics` 的 Frigate metrics endpoint。Frigate publisher 不使用 username/password/auth 選項。
- ASUS router 發布需要 `ssh` client 存取權限
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
pip install paho-mqtt psutil
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
- `HA_MQTT_PORT`，預設 `1883`
- `HA_MQTT_TOPIC_PREFIX`，預設 `homelab-ha-discovery`
- `HA_MQTT_USERNAME`，選用 MQTT username
- `HA_MQTT_PASSWORD`，選用 MQTT password
- `HA_MQTT_CLIENT_ID`，選用 MQTT client ID
- `MQTT_TOPIC`，供單一 state topic 發布器選用的 state topic 覆寫

不要將 MQTT 憑證存放在此 repository 中。對 systemd service 或 timer，請優先使用 repository 外部的環境檔，例如 `/etc/homelab-ha-discovery/mqtt.env`，並且只允許 service user 或 root 讀取。

環境檔範例：

```bash
HA_MQTT_HOST=mqtt-server-ip
HA_MQTT_PORT=1883
HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery
HA_MQTT_USERNAME=your-user
HA_MQTT_PASSWORD=your-password
```

## 乾淨主機 systemd 安裝器

可以從 checkout 將乾淨的 Debian 主機 bootstrap 起來：

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc
```

`bootstrap` 會將目前 checkout 複製到 `/opt/homelab-ha-discovery`，如果該目錄
已存在，除非傳入 `--force-copy`，否則會拒絕取代；接著建立
`/opt/homelab-ha-discovery/.venv`、安裝 `requirements.txt`、建立
`/etc/homelab-ha-discovery`，並寫入可審閱的
`/etc/homelab-ha-discovery/host-metrics.json`。複製時會排除 `.git`、`.venv`、
caches 與本機 session artifacts。

`--force-copy` 只會取代已安裝的 app 目錄。如果
`/etc/homelab-ha-discovery/host-metrics.json` 已存在，`bootstrap` 會保留它；
除非同時傳入 `--force-config`：

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc --force-copy --force-config
```

若只要重新產生 `host-metrics.json`，不複製 app、不重建 virtual environment，
請執行 detect 並加上 `--force`：

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py detect --ha-device-id hpc --force
```

`--force-config` 和 `detect --force` 都會取代整個產生的 config，所以請先保留任何
手動修改。

Debian package 安裝必須明確選用：

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc --install-system-packages
```

如果 `/etc/homelab-ha-discovery/mqtt.env` 不存在，`bootstrap` 會用可編輯的範例
設定建立它，權限為 `600`，然後印出警告。請在啟用 services 前編輯該檔案：

```bash
sudo editor /etc/homelab-ha-discovery/mqtt.env
sudo editor /etc/homelab-ha-discovery/host-metrics.json
```

審閱偵測出的 metrics config 後，產生並啟用長時間執行的 systemd services：

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py install
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py enable --now
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py logs --follow
python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py status
```

執行 `install` 時，如果已存在
`/etc/systemd/system/homelab-ha-discovery-*.service` 檔案且 stdin 是互動式，
安裝器會先詢問是否移除。回答 yes 會先移除這些產生的 unit files，再依照目前的
`host-metrics.json` 寫入 units；回答 no 則保留它們。若是 scripted runs，可傳入
`--clean-existing-units` 不詢問直接移除，或傳入 `--no-clean-existing-units`
不詢問直接保留。這個 cleanup 只會移除符合名稱的 unit files；不會停止 services，
也不會修改 `host-metrics.json`。

units 安裝完成後，安裝器也可以管理產生的 services：

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py logs
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py logs --follow --lines 200 --since "1 hour ago"
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py restart
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py stop
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py disable --now
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py uninstall
```

`logs` 會讀取產生 units 的 journal。`restart`、`stop` 與 `disable` 會操作目前
`host-metrics.json` 描述的 units；`disable --now` 也會停止它們。`uninstall`
會掃描符合名稱的產生 unit files、停止並停用這些 units、只移除產生的
`homelab-ha-discovery-*.service` files，然後重新載入 systemd。它會保留 app
目錄、`host-metrics.json`、`mqtt.env`、MQTT retained discovery config，以及
Home Assistant entities。

產生的 units 會使用 `EnvironmentFile=-/etc/homelab-ha-discovery/mqtt.env`，但
當真正的 env 檔不存在時，`enable --now` 會拒絕 enable/start services，除非傳入
`--allow-missing-mqtt-env`。這些 units 會以長時間執行的 `--timer` 模式執行現有
publishers。預設 interval 為 CPU 和 GPU `5.0` 秒、磁碟和 NVMe SMART `60.0`
秒、network `1.0` 秒、Docker containers `60.0` 秒、Frigate `10.0` 秒、
ASUS router CPU `1.0` 秒、ASUS router network `1.0` 秒，以及 ASUS router
connected clients `1.0` 秒。
產生的 `host-metrics.json` 也會包含 top-level
`timer_publish_discovery_config`，預設值為 `60.0`，因此產生的 services 會每
60 秒重新發布保留的 Home Assistant discovery config。將它設為 `null` 可全域
停用；也可以在個別 service entry 加入 `timer_publish_discovery_config` 來覆寫該
service 的設定。

任何 service entry 都可以加入 `expire_after`，用來設定該 publisher 的 Home
Assistant discovery expiry。`null` 或省略時會保留 publisher 預設值：timer-mode
services 會把 `expire_after` 設為其 `timer` 的三倍，而 one-shot manual runs
預設不會設定 expiry。將 `expire_after` 設為 `0` 可省略 expiry，也可以設定其他
非負秒數覆寫。

Detect/bootstrap 也會加入停用狀態的 Docker container template entry：

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

Docker entry 預設使用 label filtering，避免 Home Assistant 塞滿暫時性或內部
containers。移除 `include_label` 會發布所有目前 running containers，加入
`"all": true` 會包含 stopped containers，也可以加入 `docker_command` 使用非預設
Docker CLI 路徑，或加入 `"debug": true` 將 Docker publisher progress 印到
service journal。產生的 `"expire_after": null` 會保留通用 timer-mode 預設，也就是
service timer 的三倍；設定 `"expire_after": 0` 可停用 expiry，也可設定其他非負秒數覆寫。
Service user 必須能讀取 Docker state。加入 `docker` group 是常見做法，但 Docker
socket access 實質上等同 root 權限，應謹慎處理。

Detect/bootstrap 會用短 HTTP timeout probe 本機 Frigate metrics endpoint。如果
`http://127.0.0.1:5000/api/metrics` 可連線，會加入啟用的 Frigate service entry：

```json
{
  "type": "frigate",
  "enabled": true,
  "timer": 10.0,
  "url": "http://127.0.0.1:5000/api/metrics",
  "expire_after": null,
  "missing_requirements": []
}
```

如果 endpoint 無法連線，detect/bootstrap 會加入相同但停用的 entry，並附上在
Frigate running 後再啟用的 note。Publisher 使用 Python standard library HTTP
client，且不支援 username/password/auth 參數。加入 `"debug": true` 可將 collection
和 publish progress 印到 service journal。

Detect/bootstrap 也會加入停用狀態的 ASUS router template entries，且不會透過
SSH probe router：

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

請在啟用前編輯這些 entries。若要監控多台 routers，可新增更多 ASUS router
entries；請保持每個 `router_name` 穩定，因為它會用於產生的 service 名稱、
MQTT topics 和 Home Assistant unique IDs。Connected-client entries 可加入
`client_list_command` 來覆寫預設的遠端 command。Router network entries 會用
`router_name` 和 `dev` 的組合產生 unit 名稱，因此同一台 router 的多個
interfaces 會保持分離。Router network entries 可加入 `network_command` 來覆寫
預設的遠端 `/proc/net/dev` sampler。

安裝器不會設定 sudoers。磁碟與 NVMe SMART publishers 會執行
`sudo smartctl -a <dev>`，因此如果這些 services 不會以 root 執行，請為 service
user 設定非互動式 sudo 權限。

若要無害預覽，請傳入 `--dry-run`。若要測試或使用非預設 layout，安裝器的
subcommands 也接受 `--app-dir`、`--config-dir` 與 `--systemd-dir`。

## 使用方式

請從 repository root 執行。

請以 `--ha-device-id` 傳入穩定的 Home Assistant/MQTT device identity。它會用於
MQTT topics、Home Assistant unique IDs、device identifiers 與 sensor 名稱；
請保持穩定，避免 Home Assistant 建立重複 entities。`--dev` 是獨立參數，在需要時
仍用來指定磁碟路徑、NVMe controller 路徑或 network interface component。

所有會建立 Home Assistant discovery config 的 publishers 都接受
`--expire-after SECONDS`。它只影響 discovery config。One-shot mode 預設不設定
expiry。`--timer` mode 中，如果省略 `--expire-after`，預設會使用 timer 值的三倍，
例如 `--timer 60` 會設定 `expire_after=180`。使用 `--expire-after 0` 可省略
expiry，也可以傳入其他非負秒數覆寫。

CPU 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc
```

NVIDIA GPU 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc
```

未指定 `--gpu` 時，會依照 `nvidia-smi` 的列順序將所有偵測到的 NVIDIA
GPU 發布為 `gpu0`、`gpu1`，以此類推。若只要發布單一 GPU，請傳入其從
0 開始的 index：

```bash
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --gpu 0
```

磁碟 SMART 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda
```

磁碟 SMART 發布器會在本機執行 `sudo smartctl -a <dev>`。請在此 repository
外部設定 sudo，讓 service user 可以非互動式執行所需的 `smartctl` 指令。
MQTT 和 Home Assistant discovery 中的磁碟 component 會由 `--dev` 的 basename
產生，例如 `/dev/sda` 會使用 `sda`。

NVMe SMART 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0
```

NVMe SMART 發布器也會在本機執行 `sudo smartctl -a <dev>`。請為每個 NVMe
controller 執行一個 process 或 service，例如 `/dev/nvme0`、`/dev/nvme1`
等等。MQTT 和 Home Assistant discovery 中的 NVMe component 會由 `--dev`
的 basename 產生，例如 `/dev/nvme0` 會使用 `nvme0`。

Network 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0
```

Network 發布器會在本機使用 `psutil.net_io_counters(pernic=True)`。`--dev`
必須符合 network interface key，例如 `ppp0`。未使用 `--timer` 時，它會間隔
一秒取得兩次樣本，並發布一次計算出的 throughput state。速度會以 `Mbps`
發布，其中 `Mbps` 代表每秒 megabits，並以 1,000,000 bits per second 計算。
數值會四捨五入到小數點後三位；`0.001` 代表 1 Kbps，`1.000` 代表 1 Mbps。

Docker container 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc
```

Docker container 發布器會在本機執行 Docker CLI commands，並在每次執行時動態列舉
目前 running containers。它會為每個被納入的 container 發布一組 Home Assistant
discovery 和一個 state payload，例如 `plex`、`gitlab`、`nginx` 會各自有獨立
payload。Container component 會優先使用 `homelab-ha-discovery.component`
label，若沒有則由 container name 產生。不要用 container ID 作為穩定的 Home
Assistant identity，因為 container recreate 後 ID 會改變。如果兩個 containers
解析成相同 component，腳本會在發布前結束。Discovery 和 state messages 會在每個
publish cycle 用同一個 MQTT connection 批次發布。

Production 建議使用 Docker label filtering：

```bash
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true
```

`homelab-ha-discovery.enabled` 會被視為 boolean opt-in label。傳入
`--include-label homelab-ha-discovery.enabled` 等同於
`--include-label homelab-ha-discovery.enabled=true`。設定
`homelab-ha-discovery.enabled=false` 的 containers 會被排除，而傳入
`--include-label homelab-ha-discovery.enabled=false` 會直接以錯誤結束。

使用 `--all` 可包含 stopped containers；使用 `--docker-command` 可指定非預設的
Docker CLI 路徑。Network speeds 會由兩次 `docker stats` samples 計算，並以
`Mbps` 發布，其中 `Mbps` 代表每秒 megabits，並以 1,000,000 bits per second
計算。數值會四捨五入到小數點後三位。Docker network counters reset 時，例如
container restart 後，該 interval 會回報 `0.0` speed。

Docker 和其他 publishers 使用相同的 `--expire-after` 行為，因此 Home Assistant
可以在錯過更新後將 stale container sensors 標記為 unavailable。使用
`--expire-after 0` 可永不 expire，也可以傳入其他秒數：

```bash
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0 --expire-after 0
```

Troubleshooting 時可加入 `--debug`。它會將 timestamped sample counts、included
containers、timer sleeps、discovery decisions、state topics 和 payloads 印到 stderr：

```bash
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0 --timer-publish-discovery-config 60.0 --debug
```

Frigate 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_frigate_metrics.py --ha-device-id hpc
```

Frigate publisher 預設會從 `http://127.0.0.1:5000/api/metrics` 讀取
Prometheus text metrics。可用 `--url` 指向其他 Frigate endpoint：

```bash
python3 src/homelab_ha_discovery/scripts/publish_frigate_metrics.py --ha-device-id hpc --url http://127.0.0.1:5000/api/metrics
```

它會發布一個 shared JSON state payload，內容包含 `system`、`cameras`、
`detectors`、`gpus` 和 `storage`。Storage 的 `frigate_storage_free_bytes` 和
`frigate_storage_used_bytes` 會從 bytes 轉成 decimal `GB`，並四捨五入到小數點後
三位。Publisher 會在發布 discovery config 或 state 前先驗證 HTTP errors、
malformed Prometheus text，以及缺少 required metric families。加入 `--debug`
可將 HTTP collection、discovery、state topic 和 payload progress 印到 stderr。

ASUS router CPU 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address
```

ASUS router CPU 發布器會透過 SSH 在遠端執行 `top -bn1` 和
`cat /sys/class/thermal/thermal_zone*/temp`。`--ssh-port` 預設為 `22`。
`--ha-device-id` 仍是 Home Assistant/MQTT device identity；`--router-name`
會被 normalize 成 router component，例如 `ASUS AX86U` 會變成
`asus_ax86u`。溫度輸出會被視為 millidegrees Celsius，並發布最高的有效
thermal zone 數值。每個遠端 SSH command 都有 10 秒 timeout。如果 router
需要不同 commands，可用 `--top-command` 或 `--temperature-command` 覆寫；
產生的 systemd config entry 也可以加入 `top_command` 和
`temperature_command`。

ASUS router network 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22
```

ASUS router network 發布器會為 `--dev` 產生遠端 `/proc/net/dev` sampler，透過
SSH 間隔一秒讀取兩次 RX/TX bytes，確認 counters 存在且未遞減，並以 `Mbps`
發布下載/上傳速度。`--ssh-port` 預設為 `22`。`--ha-device-id` 仍是 Home
Assistant/MQTT device identity；`--router-name` 會被 normalize 成 router
component，例如 `ASUS AX86U` 會變成 `asus_ax86u`；`--dev` 是 router interface
component，例如 `eth0`。如果 router 需要不同 command，可用
`--network-command` 覆寫；產生的 systemd config entry 也可以加入
`network_command`。

ASUS router connected-client 指標：

```bash
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22
```

ASUS router connected-client 發布器會透過 SSH 在遠端執行
`cat /var/lib/misc/dnsmasq.leases; echo "---END_LEASES---"; cat /tmp/clientlist.json`。
它會遞迴走訪巢狀的 `clientlist.json` objects，所以像 top-level AP MAC wrapper 也可
以處理。它會發布 ASUS interface sections（例如 `2G`、`5G` 和 `wired_mac`）底下
找到的每個 MAC；只存在於 DHCP leases、但不存在於 `clientlist.json` 的 rows 不會
被納入。MAC addresses 會 normalize 成大寫。DHCP hostnames 會先依 MAC 比對，再
以 IP fallback。缺少 DHCP hostname 時會發布 `" - "`，缺少 RSSI（例如 wired
clients）時會發布 `"N/A"`。如果 router 需要不同 command，可用
`--client-list-command` 覆寫；產生的 systemd config entry 也可以加入
`client_list_command`。

若要手動 troubleshooting，請加入 `--debug`，它會將進度訊息印到 stderr。
對 connected-client runs，debug output 也會包含 raw SSH output（會放在
begin/end markers 之間）、dnsmasq lease counts、`clientlist.json`
top-level keys、matched interface sections、MAC counts，以及 sample extracted
clients：

```bash
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22 --timer 1.0 --timer-publish-discovery-config 60.0 --debug
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22 --timer 1.0 --timer-publish-discovery-config 60.0 --debug
sudo /opt/homelab-ha-discovery/.venv/bin/python /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --ssh-port 22 --timer 1.0 --timer-publish-discovery-config 60.0 --debug
```

若要頻繁透過 systemd timer 執行，請在一般執行已註冊 discovery config 後使用 `--publisher-only`：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_frigate_metrics.py --ha-device-id hpc --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --publisher-only
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --publisher-only
```

若要使用長時間執行的服務模式，請使用 `--timer SECONDS`。大多數發布器會立即發布第一次指標，之後腳本會在每次發布嘗試之間休眠。本機 network 指標會先建立 baseline，等待一個 interval 後，才發布第一次計算出的速度。Docker container 指標也會先建立 baseline，並在每個 interval 重新列舉 containers。ASUS router network 指標會在每次發布嘗試期間執行一秒遠端 sample：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --timer 5.0
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --timer 1.0
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0
python3 src/homelab_ha_discovery/scripts/publish_frigate_metrics.py --ha-device-id hpc --timer 10.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --timer 1.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0
```

未使用 `--publisher-only` 時，`--timer` 會在啟動時發布一次 discovery config，之後每個 interval 只發布 metric state。對本機 network 和 Docker container 指標來說，啟動時的 discovery config 會在 baseline interval 後、第一次計算出的 metric state 之前發布。新納入的 Docker containers 會在下一個 timer interval 發布 discovery config，並在有前一次 network sample 後發布 metric state。使用 `--timer --publisher-only` 時，每個 interval 只發布 metric state。省略 `--expire-after` 時，timer-mode discovery config 會將 `expire_after` 設為 timer 值的三倍。

若要在長時間執行的服務模式中定期重新發布保留的 discovery config，請加入 `--timer-publish-discovery-config SECONDS`：

```bash
python3 src/homelab_ha_discovery/scripts/publish_cpu_metrics.py --ha-device-id hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_gpu_metrics.py --ha-device-id hpc --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_sdx_metrics.py --ha-device-id hpc --dev /dev/sda --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_nvme_metrics.py --ha-device-id hpc --dev /dev/nvme0 --timer 5.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_network_metrics.py --ha-device-id hpc --dev ppp0 --timer 1.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_docker_container_metrics.py --ha-device-id hpc --include-label homelab-ha-discovery.enabled=true --timer 60.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_frigate_metrics.py --ha-device-id hpc --timer 10.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --dev eth0 --ssh-user router-user --ssh-ip router-ip-address --timer 1.0 --timer-publish-discovery-config 60.0
python3 src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py --ha-device-id hpc --router-name "ASUS AX86U" --ssh-user router-user --ssh-ip router-ip-address --timer 1.0 --timer-publish-discovery-config 60.0
```

如果未設定 `--timer-publish-discovery-config`，timer 行為會維持只在啟動時發布一次 discovery。此選項需要 `--timer`，且不能與 `--publisher-only` 一起使用。

## MQTT Topics

使用預設 topic prefix 和 `--ha-device-id hpc` 時，CPU 指標會將 state 發布到：

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

使用 `--ha-device-id hpc --router-name "ASUS AX86U"` 時，ASUS router CPU
指標會將 state 發布到：

```text
homelab-ha-discovery/asus_ax86u/cpu/metrics/hpc
```

Payload：

```json
{"CPU Usages":37.8,"Temperature":54.0}
```

Discovery topics：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_cpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_cpu_temperature/config
```

Home Assistant sensor 名稱也會使用 router name，例如 `hpc ASUS AX86U CPU
Usage`。因為 normalized router name 會包含在 Home Assistant unique IDs 中，
變更 `--router-name` 會改變 entities。

使用 `--ha-device-id hpc --router-name "ASUS AX86U" --dev eth0` 時，ASUS
router network 指標會將 state 發布到：

```text
homelab-ha-discovery/asus_ax86u/eth0/metrics/hpc
```

Payload：

```json
{"Download Speed":0.001,"Upload Speed":1.0}
```

Discovery topics：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_eth0_download_speed/config
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_eth0_upload_speed/config
```

Home Assistant sensor 名稱會包含 router name 和 interface，例如
`hpc ASUS AX86U eth0 Download Speed`。因為 normalized router name 和 interface
會包含在 Home Assistant unique IDs 中，變更 `--router-name` 或 `--dev` 都會改變
entities。

使用 `--ha-device-id hpc --router-name "ASUS AX86U"` 時，ASUS router
connected-client 指標會將 state 發布到：

```text
homelab-ha-discovery/asus_ax86u/connected_clients/metrics/hpc
```

Payload：

```json
[{"mac":"8C:FD:49:49:7B:58","ip":"192.168.4.72","rssi":"-68","interface":"2G","name":"mushroom_02_pc0"}]
```

Discovery topic：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_asus_ax86u_connected_clients/config
```

Home Assistant discovery 會建立一個 count sensor，例如 `hpc ASUS AX86U
Connected Clients`；它的 value template 會用 `{{ value_json | count }}` 讀取
array 長度。詳細的 client list 會保留在 MQTT state payload 中。

使用 `--ha-device-id hpc` 時，未指定 `--gpu` 的 NVIDIA GPU 指標會將 state
發布到：

```text
homelab-ha-discovery/gpu/usages/hpc
```

Payload：

```json
{"gpu0":{"GPU Card Name":"NVIDIA GeForce RTX 5060 Ti","GPU Usages":55.2,"Memory Usage":41.7,"Temperature":72},"gpu1":{"GPU Card Name":"NVIDIA GeForce RTX 3060","GPU Usages":30.0,"Memory Usage":22.5,"Temperature":61},"gpu2":{"GPU Card Name":"NVIDIA RTX A4000","GPU Usages":80.4,"Memory Usage":70.1,"Temperature":68}}
```

使用 `--ha-device-id hpc --gpu 0` 時，NVIDIA GPU 指標只會將 `gpu0` 發布到：

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

使用 `--ha-device-id hpc --dev /dev/sda` 時，磁碟 SMART 指標會將 state 發布到：

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

使用 `--ha-device-id hpc --dev /dev/nvme0` 時，NVMe SMART 指標會將 state 發布到：

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

使用 `--ha-device-id hpc --dev ppp0` 時，network 指標會將 state 發布到：

```text
homelab-ha-discovery/ppp0/metrics/hpc
```

Payload：

```json
{"Download Speed":0.001,"Upload Speed":1.0}
```

Discovery topics：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_ppp0_download_speed/config
homeassistant/sensor/homelab_ha_discovery_hpc_ppp0_upload_speed/config
```

Network speed sensor 使用 `Mbps`，其中 `Mbps` 代表每秒 megabits，並以
1,000,000 bits per second 計算。數值會四捨五入到小數點後三位；`0.001`
代表 1 Kbps，`1.000` 代表 1 Mbps。Home Assistant sensor 名稱也會使用 network
interface component，例如 `hpc ppp0 Download Speed`。因為 interface component
會包含在 Home Assistant unique ID 中，變更 `--dev` 會改變 entities。

使用 `--ha-device-id hpc` 時，Docker container 指標會為每個被納入的 container
發布一個 state topic。以名為 `plex` 的 container 為例，state topic 是：

```text
homelab-ha-discovery/hpc/docker/plex/metrics
```

Payload：

```json
{"State":"running","Health":"healthy","Restart Count":2,"CPU Usage":2.318,"Memory Usage MB":512.4,"Memory Limit MB":8192.0,"Memory Usage Percent":6.25,"Download Speed":0.001,"Upload Speed":1.0}
```

Discovery topics：

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

如果 `plex`、`gitlab` 和 `nginx` 都被納入，每個 container 都會有自己的 state
topic 和 discovery topics。被移除或改名的 containers 不會自動從 Home Assistant
刪除；舊的 retained discovery config 只有在明確需要時才應手動清理。

使用 `--ha-device-id hpc` 時，Frigate 指標會發布一個 shared state topic：

```text
homelab-ha-discovery/frigate/metrics/hpc
```

Payload：

```json
{"system":{"CPU Usage":12.346,"Memory Usage":45.679},"cameras":{"front door":{"Camera FPS":5.0,"Process FPS":4.5,"Skipped FPS":0.0,"Detection FPS":3.25}},"detectors":{"coral":{"Inference Speed":0.011}},"gpus":{"nvidia 0":{"GPU Usage":33.333,"Memory Usage":55.556}},"storage":{"/media/frigate/recordings":{"Free GB":1.235,"Used GB":9.877}}}
```

Discovery topics 會包含 normalized Frigate components：

```text
homeassistant/sensor/homelab_ha_discovery_hpc_frigate_system_cpu_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_frigate_system_memory_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_frigate_camera_front_door_camera_fps/config
homeassistant/sensor/homelab_ha_discovery_hpc_frigate_detector_coral_inference_speed/config
homeassistant/sensor/homelab_ha_discovery_hpc_frigate_gpu_nvidia_0_usage/config
homeassistant/sensor/homelab_ha_discovery_hpc_frigate_storage_media_frigate_recordings_free_gb/config
```

Frigate discovery value templates 會從 shared JSON payload 讀取。CPU、memory 和
GPU usage 使用 `%`；camera frame rates 使用 `fps`；detector inference speed
使用 `s`；轉換後的 storage values 使用 `GB`。

如果設定了 `MQTT_TOPIC`，有單一 state topic 的發布器會將它作為 state topic，
且 discovery config 會指向同一個 topic。Docker container 指標永遠使用每個
container 各自的 state topic。

Discovery config 會被 retain。Metric state 預設不 retain。每個 publish cycle 會用
一個 MQTT connection 發布已 queue 的 discovery 和 state messages。

## 開發

Collectors 位於 `src/homelab_ha_discovery/collectors/`；可執行腳本位於 `src/homelab_ha_discovery/scripts/`。

相關驗證指令：

```bash
python3 -m py_compile src/homelab_ha_discovery/mqtt.py
python3 -m py_compile src/homelab_ha_discovery/discovery.py
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
python3 -m py_compile src/homelab_ha_discovery/collectors/frigate_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_frigate_metrics.py
python3 -m py_compile src/homelab_ha_discovery/collectors/router_asus_ssh.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_asus_router_cpu_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_asus_router_network_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/publish_asus_router_connected_clients_metrics.py
python3 -m py_compile src/homelab_ha_discovery/scripts/install_debian_host_systemd.py
python3 -m unittest discover -s tests
```

如果可用，也請執行 `pytest`。

## 授權

此專案採用 MIT License 授權。請見 [LICENSE](LICENSE)。
