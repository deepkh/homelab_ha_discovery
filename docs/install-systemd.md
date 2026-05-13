# Systemd install

This page keeps systemd installation details outside the README.

## Recommended flow

Bootstrap config files:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc
```

Edit generated config:

```bash
sudo editor /etc/homelab-ha-discovery/mqtt.env
sudo editor /etc/homelab-ha-discovery/host-metrics.json
```

Install from the managed copy:

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py install
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py enable --now
```

## Useful commands

Check service status:

```bash
systemctl status 'homelab-ha-discovery-*'
```

Follow logs:

```bash
journalctl -u 'homelab-ha-discovery-*' -f
```

Disable services:

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py disable
```

Uninstall services:

```bash
sudo python3 /opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/install_debian_host_systemd.py uninstall
```

## Notes

- Keep secrets in `/etc/homelab-ha-discovery/mqtt.env`.
- Do not commit generated local config files with real credentials.
- Prefer checking one service first before enabling all services.
