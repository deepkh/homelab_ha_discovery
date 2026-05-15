"""GPU detection helpers for generated host metrics config."""

from __future__ import annotations

import json
from pathlib import Path
import re

from homelab_ha_discovery.installer.detect.commands import (
    command_exists,
    command_output,
)


def parse_nvidia_gpu_indexes(output: str) -> list[int]:
    indexes: list[int] = []
    for line in output.splitlines():
        match = re.match(r"\s*GPU\s+(\d+):", line)
        if match is not None:
            indexes.append(int(match.group(1)))
    return sorted(set(indexes))

def detect_nvidia_gpu_indexes() -> list[int]:
    if not command_exists("nvidia-smi"):
        return []
    return parse_nvidia_gpu_indexes(command_output(["nvidia-smi", "-L"]))

def parse_amd_rocm_gpu_indexes(output: str) -> list[int]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = None

    indexes: set[int] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            match = re.match(r"\s*(?:card|gpu)(\d+)\s*$", key, re.IGNORECASE)
            if match is not None:
                indexes.add(int(match.group(1)))
        return sorted(indexes)

    for line in output.splitlines():
        match = re.search(r"(?:GPU|card)\s*\[?(\d+)\]?", line, re.IGNORECASE)
        if match is not None:
            indexes.add(int(match.group(1)))
    return sorted(indexes)

def detect_amd_rocm_gpu_indexes() -> list[int]:
    if not command_exists("rocm-smi"):
        return []
    return parse_amd_rocm_gpu_indexes(
        command_output(["rocm-smi", "--showproductname", "--json"])
    )

def device_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"(\d+)$", path.name)
    if match is None:
        return (10_000, path.name)
    return (int(match.group(1)), path.name)

def first_device_path(paths: list[Path]) -> str | None:
    if not paths:
        return None
    return str(sorted(paths, key=device_sort_key)[0])

def detect_intel_qsv_gpu_devices(
    dri_dir: Path = Path("/dev/dri"),
) -> dict[str, str | None]:
    return {
        "render_device": first_device_path(list(dri_dir.glob("renderD*"))),
        "drm_device": first_device_path(list(dri_dir.glob("card*"))),
    }
