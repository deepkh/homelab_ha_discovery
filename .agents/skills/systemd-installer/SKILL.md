---
name: systemd-installer
description: Use when changing the Debian host systemd installer, bootstrap/config generation, service templates, enable/disable behavior, logs, restart behavior, or uninstall behavior.
---

# Systemd installer

## Goals

The installer should make it easy to run selected publishers as systemd services on a Debian host.

## Expected flow

```text
bootstrap -> edit config -> install -> enable --now -> check logs
```

## Config locations

Default config directory:

```text
/etc/homelab-ha-discovery
```

Common files:

```text
/etc/homelab-ha-discovery/mqtt.env
/etc/homelab-ha-discovery/host-metrics.json
```

Managed install path:

```text
/opt/homelab-ha-discovery
```

## Safety rules

- Do not overwrite existing user config without backup or explicit intent.
- Do not embed MQTT credentials in service files if an env file can be used.
- Do not start or stop services unless explicitly asked.
- Keep uninstall behavior clear and conservative.

## Validation checklist

When changing installer behavior:

- bootstrap creates expected files
- install writes expected systemd units
- enable starts only intended services
- disable stops/disables intended services
- uninstall removes units safely
- docs/install-systemd.md is updated
