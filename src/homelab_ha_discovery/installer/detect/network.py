"""Network interface detection helpers for generated host metrics config."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from homelab_ha_discovery.installer.config_io import DEFAULT_TIMERS


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""

def default_route_interfaces() -> set[str]:
    route_path = Path("/proc/net/route")
    interfaces: set[str] = set()
    try:
        lines = route_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return interfaces

    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        interface, destination, _gateway, flags = fields[:4]
        try:
            route_is_up = bool(int(flags, 16) & 0x2)
        except ValueError:
            route_is_up = False
        if destination == "00000000" and route_is_up:
            interfaces.add(interface)
    return interfaces

def detect_network_interfaces() -> list[dict[str, Any]]:
    sys_net = Path("/sys/class/net")
    if not sys_net.exists():
        return []
    default_routes = default_route_interfaces()
    interfaces = []
    for path in sorted(sys_net.iterdir(), key=lambda item: item.name):
        if path.name == "lo":
            continue
        operstate = read_text(path / "operstate") or "unknown"
        if default_routes:
            enabled = path.name in default_routes
            note = "default route interface" if enabled else "not a default route"
        else:
            enabled = operstate in {"up", "unknown"}
            note = f"operstate={operstate}"
        interfaces.append(
            {
                "type": "network",
                "enabled": enabled,
                "dev": path.name,
                "timer": DEFAULT_TIMERS["network"],
                "detected_operstate": operstate,
                "note": note,
            }
        )
    return interfaces
