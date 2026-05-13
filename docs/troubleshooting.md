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

## Router metrics missing

Check:

- router SSH is enabled
- host/IP is correct
- credentials or SSH key are valid
- command works manually over SSH
