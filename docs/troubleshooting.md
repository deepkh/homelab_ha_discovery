# Troubleshooting

## MQTT connection failed

Check:

```bash
HA_MQTT_HOST
HA_MQTT_PORT
HA_MQTT_USERNAME
HA_MQTT_PASSWORD
```

Then test broker access using a normal MQTT client.

## Entity does not appear in Home Assistant

Check:

- Home Assistant MQTT integration is enabled
- discovery topic exists
- discovery message is retained
- state topic exists
- discovery config `state_topic` matches the real state topic
- entity has a stable `unique_id`

## Systemd service failed

Check logs:

```bash
journalctl -u 'homelab-ha-discovery-*' -n 200 --no-pager
```

Check environment/config:

```bash
sudo systemctl cat homelab-ha-discovery-<name>.service
```

## SMART/NVMe metrics missing

Check:

- `smartctl` is installed
- the target disk path is correct
- required permissions are available
- the disk supports the requested SMART fields

## NVIDIA metrics missing

Check:

```bash
nvidia-smi
```

If `nvidia-smi` fails, fix the NVIDIA driver/tooling first.

## AMD ROCm metrics missing

Check:

```bash
rocm-smi --showproductname --showuse --showmemuse --showtemp --json
```

If `rocm-smi` fails or returns no cards, fix the AMD ROCm driver/tooling first.

## Intel QSV metrics missing

Check DRI devices and Intel media tooling:

```bash
ls -l /dev/dri
vainfo --display drm --device /dev/dri/renderD128
intel_gpu_top -J -s 1000 -o -
```

Check that FFmpeg can see QSV support when the service is meant to track media
transcoding load:

```bash
ffmpeg -hide_banner -hwaccels
ffmpeg -hide_banner -init_hw_device qsv=hw:/dev/dri/renderD128 -f lavfi -i nullsrc -frames:v 1 -f null -
```

Install `intel-gpu-tools` for `intel_gpu_top` and `vainfo` for VA-API checks.
The systemd detector enables Intel QSV only when a render device and
`intel_gpu_top` are available.

## Podman metrics missing

Check root Podman:

```bash
podman ps
podman stats --no-stream --format=json
```

For rootless Podman, run the same commands as the configured user and verify the
generated service has the expected runtime directory:

```bash
sudo systemctl cat homelab-ha-discovery-<name>.service
```

If `/run/user/<uid>` is missing for a rootless service, enable linger for that user
or make sure the user's session services are running.

If a rootless service logs `Could not read env file ... mqtt.env ... Permission
denied`, regenerate the systemd units with the current installer and restart the
service. The generated unit should include
`HOMELAB_HA_DISCOVERY_SKIP_ENV_FILES=1`; do not loosen `mqtt.env` permissions to
work around this.

## Router metrics missing

Check:

- router SSH is enabled
- host/IP is correct
- credentials or SSH key are valid
- command works manually over SSH
