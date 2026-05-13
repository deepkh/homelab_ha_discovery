# Systemd install

This page keeps systemd installation details outside the README.

## Recommended flow

Install the required Debian packages if the host does not already have them:

```bash
sudo ./scripts/install-system-packages-debian.sh
```

Bootstrap the managed app copy and config files:

```bash
sudo ./scripts/bootstrap-debian-host.sh --ha-device-id hpc
```

Bootstrap detects local GPU tooling and writes GPU service entries to
`host-metrics.json` when available. NVIDIA uses `nvidia-smi`; AMD ROCm uses
`rocm-smi`.

Bootstrap also detects running root Podman containers when `podman` is available.
Rootless Podman is opt-in per user:

```bash
sudo ./scripts/bootstrap-debian-host.sh --ha-device-id hpc --rootless-podman-user alice --rootless-podman-user media
```

The bootstrap wrapper installs a small `/usr/local/bin/hhdctl` command wrapper
that points at the managed copy under `/opt/homelab-ha-discovery`.

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

Render units and enable services:

```bash
sudo hhdctl systemd render
sudo hhdctl systemd enable --now
sudo hhdctl systemd logs --follow
```

## Useful commands

Render unit files without enabling services:

```bash
sudo hhdctl systemd render
```

Check service status:

```bash
sudo hhdctl systemd status
```

Follow logs:

```bash
sudo hhdctl systemd logs --follow
```

Disable services:

```bash
sudo hhdctl systemd disable --now
```

Uninstall services:

```bash
sudo hhdctl systemd uninstall
# or:
sudo ./scripts/uninstall-debian-host.sh
```

## Direct hhdctl commands

The bootstrap wrapper is equivalent to this sequence:

```bash
sudo python3 src/homelab_ha_discovery/scripts/hhdctl.py app install
sudo hhdctl config init-mqtt-env
sudo hhdctl config detect --ha-device-id hpc
```

Podman detection options:

```bash
sudo hhdctl config detect --ha-device-id hpc --rootless-podman-user alice
sudo hhdctl config detect --ha-device-id hpc --rootless-podman-uid 1001
sudo hhdctl config detect --ha-device-id hpc --auto-discover-rootless-podman
sudo hhdctl config detect --ha-device-id hpc --podman-socket /run/podman/podman.sock
```

## Notes

- Keep secrets in `/etc/homelab-ha-discovery/mqtt.env`.
- Keep `/etc/homelab-ha-discovery/mqtt.env` readable by root only; generated
  systemd services pass these settings to the publisher process.
- Do not commit generated local config files with real credentials.
- Prefer checking one service first before enabling all services.
- GPU services may use `gpu_indexes` to publish multiple cards from one timer loop.
- Rootless Podman containers are detected only for users passed with
  `--rootless-podman-user`, UIDs passed with `--rootless-podman-uid`, or sockets
  found by `--auto-discover-rootless-podman`.
- Rootless Podman usually requires the user's runtime directory to exist. If the
  service cannot access `/run/user/<uid>`, enable linger for that user or start the
  user's login/session services before relying on the rootless service.
- `install_debian_host_systemd.py` remains available for compatibility. New
  installs should prefer `hhdctl`.
