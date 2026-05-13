"""Read AMD ROCm GPU metrics from rocm-smi."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from typing import Any

from homelab_ha_discovery.collectors.gpu_common import GpuMetrics, clamp_percent


NAME_KEYS = (
    "Device Name",
    "Card Series",
    "Card Model",
    "Card SKU",
    "Product Name",
    "GPU Card Name",
)
GPU_USAGE_KEYS = (
    "GPU use (%)",
    "GPU Usage (%)",
    "GPU Busy (%)",
)
MEMORY_USAGE_KEYS = (
    "GPU Memory Allocated (VRAM%)",
    "GPU Memory Usage (%)",
    "Memory Usage (%)",
    "VRAM Usage (%)",
    "VRAM use (%)",
)
TEMPERATURE_KEYS = (
    "Temperature (Sensor edge) (C)",
    "Temperature (Sensor junction) (C)",
    "Temperature (Sensor memory) (C)",
    "Temperature (C)",
)


def run_rocm_smi() -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        [
            "rocm-smi",
            "--showproductname",
            "--showuse",
            "--showmemuse",
            "--showtemp",
            "--json",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def parse_number(value: object, name: str) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value)
        if match is None:
            raise ValueError(f"Missing numeric AMD ROCm GPU value for {name}")
        number = float(match.group(0))
    else:
        raise ValueError(f"Missing numeric AMD ROCm GPU value for {name}")

    if not math.isfinite(number):
        raise ValueError(f"Invalid AMD ROCm GPU value for {name}: {number}")
    return number


def card_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, str]:
    match = re.search(r"(\d+)$", item[0])
    if match is None:
        return (10_000, item[0])
    return (int(match.group(1)), item[0])


def card_entries(data: object) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(data, dict):
        raise ValueError("Unexpected rocm-smi JSON output")

    cards: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        normalized = key.strip().lower()
        if normalized.startswith(("card", "gpu")):
            cards.append((key, value))
    return sorted(cards, key=card_sort_key)


def find_string(card: dict[str, Any], exact_keys: tuple[str, ...]) -> str:
    for key in exact_keys:
        value = card.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key, value in card.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        normalized = key.lower()
        if (
            "name" in normalized
            or "series" in normalized
            or "model" in normalized
            or "sku" in normalized
        ) and value.strip():
            return value.strip()
    raise ValueError("Missing AMD ROCm GPU card name")


def find_number(
    card: dict[str, Any],
    exact_keys: tuple[str, ...],
    name: str,
    *,
    fallback_pattern: re.Pattern[str],
) -> float:
    for key in exact_keys:
        if key in card:
            return parse_number(card[key], name)

    for key, value in card.items():
        if not isinstance(key, str):
            continue
        if fallback_pattern.search(key.lower()):
            return parse_number(value, name)
    raise ValueError(f"Missing AMD ROCm GPU metric: {name}")


def parse_gpu_metrics(rocm_smi_output: str) -> GpuMetrics:
    try:
        data = json.loads(rocm_smi_output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Unexpected rocm-smi JSON output: {exc}") from exc

    metrics: GpuMetrics = {}
    for source_key, card in card_entries(data):
        match = re.search(r"(\d+)$", source_key)
        gpu_key = f"gpu{int(match.group(1))}" if match else f"gpu{len(metrics)}"
        card_name = find_string(card, NAME_KEYS)
        gpu_usage = find_number(
            card,
            GPU_USAGE_KEYS,
            "GPU usage",
            fallback_pattern=re.compile(r"gpu.*(?:use|usage|busy).*\%"),
        )
        memory_usage = find_number(
            card,
            MEMORY_USAGE_KEYS,
            "memory usage",
            fallback_pattern=re.compile(
                r"(?:vram|mem|memory).*(?:use|usage|allocated).*\%"
            ),
        )
        temperature = find_number(
            card,
            TEMPERATURE_KEYS,
            "temperature",
            fallback_pattern=re.compile(r"(?:temperature|temp).*\(c\)"),
        )

        if gpu_key in metrics:
            raise ValueError(
                f"Duplicate AMD ROCm GPU index in rocm-smi output: {gpu_key}"
            )

        metrics[gpu_key] = {
            "GPU Card Name": card_name,
            "GPU Usages": clamp_percent(gpu_usage),
            "Memory Usage": clamp_percent(memory_usage),
            "Temperature": round(temperature),
        }

    if not metrics:
        raise ValueError("Could not find AMD ROCm GPU metrics in rocm-smi output")

    return metrics


def collect_gpu_metrics() -> GpuMetrics:
    return parse_gpu_metrics(run_rocm_smi())
