"""Storage device detection helpers for generated host metrics config."""

from __future__ import annotations

from pathlib import Path
import re


def detect_disk_devices() -> list[str]:
    sys_block = Path("/sys/block")
    if not sys_block.exists():
        return []
    devices = []
    for path in sorted(sys_block.iterdir(), key=lambda item: item.name):
        if not re.fullmatch(r"sd[a-z]+", path.name):
            continue
        dev_path = Path("/dev") / path.name
        if dev_path.exists():
            devices.append(str(dev_path))
    return devices

def detect_nvme_devices() -> list[str]:
    sys_nvme = Path("/sys/class/nvme")
    devices = []
    if sys_nvme.exists():
        for path in sorted(sys_nvme.iterdir(), key=lambda item: item.name):
            if not re.fullmatch(r"nvme\d+", path.name):
                continue
            dev_path = Path("/dev") / path.name
            if dev_path.exists():
                devices.append(str(dev_path))
    if devices:
        return devices

    return [
        str(path)
        for path in sorted(Path("/dev").glob("nvme[0-9]*"))
        if re.fullmatch(r"nvme\d+", path.name)
    ]
