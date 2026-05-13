# Systemd install

This page keeps systemd installation details outside the README.

## Recommended flow

Bootstrap config files:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc
```

Bootstrap detects local GPU tooling and writes GPU service entries to
`host-metrics.json` when available. NVIDIA uses `nvidia-smi`; AMD ROCm uses
`rocm-smi`.

Bootstrap also detects running root Podman containers when `podman` is available.
Rootless Podman is opt-in per user:

```bash
sudo python3 src/homelab_ha_discovery/scripts/install_debian_host_systemd.py bootstrap --ha-device-id hpc --rootless-podman-user alice --rootless-podman-user media
```

Rootless Podman services run as the configured user and set
`XDG_RUNTIME_DIR=/run/user/<uid>` in the generated systemd unit.
Generated services load MQTT settings through systemd `EnvironmentFile=` and set
`HOMELAB_HA_DISCOVERY_SKIP_ENV_FILES=1`, so the service process does not need
direct read access to the secret `mqtt.env` file.

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
- Keep `/etc/homelab-ha-discovery/mqtt.env` readable by root only; generated
  systemd services pass these settings to the publisher process.
- Do not commit generated local config files with real credentials.
- Prefer checking one service first before enabling all services.
- GPU services may use `gpu_indexes` to publish multiple cards from one timer loop.
- Rootless Podman containers are detected only for users passed with
  `--rootless-podman-user`.
- Rootless Podman usually requires the user's runtime directory to exist. If the
  service cannot access `/run/user/<uid>`, enable linger for that user or start the
  user's login/session services before relying on the rootless service.
