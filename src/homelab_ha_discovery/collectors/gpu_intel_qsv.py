"""Read Intel QSV/media engine metrics from intel_gpu_top."""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from typing import Any

from homelab_ha_discovery.collectors.gpu_common import GpuMetrics, clamp_percent


INTEL_GPU_TOP_SAMPLE_MS = 1000
INTEL_GPU_TOP_TIMEOUT_SECONDS = 2.5
ENGINE_NAMES = ("Render/3D", "Blitter", "Video", "VideoEnhance", "Compute")
MEDIA_ENGINE_NAMES = ("Video", "VideoEnhance")


def stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def run_intel_gpu_top() -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    command = [
        "intel_gpu_top",
        "-J",
        "-s",
        str(INTEL_GPU_TOP_SAMPLE_MS),
        "-o",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=env,
            text=True,
            timeout=INTEL_GPU_TOP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        return stream_text(exc.stdout)

    if result.returncode != 0:
        result.check_returncode()
    return result.stdout


def parse_json_samples(output: str) -> list[dict[str, Any]]:
    text = output.strip()
    if not text:
        raise ValueError("Could not find Intel QSV GPU metrics in intel_gpu_top output")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        data = parse_truncated_json_array(text, exc)

    if isinstance(data, dict):
        samples = [data]
    elif isinstance(data, list):
        samples = data
    else:
        raise ValueError("Unexpected intel_gpu_top JSON output")

    dict_samples = [sample for sample in samples if isinstance(sample, dict)]
    if not dict_samples:
        raise ValueError("Could not find Intel QSV GPU metrics in intel_gpu_top output")
    return dict_samples


def parse_truncated_json_array(
    text: str,
    original_error: json.JSONDecodeError,
) -> list[Any]:
    if not text.startswith("["):
        raise ValueError(
            f"Unexpected intel_gpu_top JSON output: {original_error}"
        ) from original_error

    decoder = json.JSONDecoder()
    samples: list[Any] = []
    position = 1
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position < len(text) and text[position] == ",":
            position += 1
            continue
        if position >= len(text) or text[position] == "]":
            break

        try:
            sample, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            break
        samples.append(sample)

    if not samples:
        raise ValueError(
            f"Unexpected intel_gpu_top JSON output: {original_error}"
        ) from original_error
    return samples


def parse_busy_value(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "value" in value:
            return parse_busy_value(value["value"], name)
        if "busy" in value:
            return parse_busy_value(value["busy"], name)
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped == "-":
            return None
        match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", stripped)
        if match is None:
            return None
        number = float(match.group(0))
    else:
        return None

    if not math.isfinite(number):
        raise ValueError(f"Invalid Intel QSV GPU value for {name}: {number}")
    return clamp_percent(number)


def engine_base_name(name: str) -> str:
    return re.sub(r"/\d+$", "", name.strip())


def parse_engine_busy(sample: dict[str, Any]) -> tuple[dict[str, float], set[str]]:
    engines = sample.get("engines")
    if not isinstance(engines, dict):
        return {}, set()

    busy_by_engine: dict[str, float] = {}
    present_engines: set[str] = set()
    for raw_name, raw_value in engines.items():
        if not isinstance(raw_name, str):
            continue
        engine_name = engine_base_name(raw_name)
        if engine_name not in ENGINE_NAMES:
            continue

        present_engines.add(engine_name)
        value = raw_value.get("busy") if isinstance(raw_value, dict) else raw_value
        busy = parse_busy_value(value, f"{raw_name} busy")
        if busy is None:
            continue

        current = busy_by_engine.get(engine_name)
        if current is None or busy > current:
            busy_by_engine[engine_name] = busy

    return busy_by_engine, present_engines


def parse_gpu_metrics(intel_gpu_top_output: str) -> GpuMetrics:
    samples = parse_json_samples(intel_gpu_top_output)
    busy_by_engine, present_engines = parse_engine_busy(samples[-1])

    engine_values = [busy for busy in busy_by_engine.values()]
    gpu_usage = max(engine_values) if engine_values else None
    qsv_available = bool(present_engines.intersection(MEDIA_ENGINE_NAMES))
    qsv_active = any(
        (busy_by_engine.get(engine_name) or 0.0) >= 1.0
        for engine_name in MEDIA_ENGINE_NAMES
    )

    return {
        "gpu0": {
            "GPU Card Name": "Intel GPU",
            "GPU Usages": gpu_usage,
            "Memory Usage": None,
            "Temperature": None,
            "QSV Available": qsv_available,
            "QSV Active": qsv_active,
            "Render/3D Busy": busy_by_engine.get("Render/3D"),
            "Blitter Busy": busy_by_engine.get("Blitter"),
            "Video Busy": busy_by_engine.get("Video"),
            "VideoEnhance Busy": busy_by_engine.get("VideoEnhance"),
            "Compute Busy": busy_by_engine.get("Compute"),
        }
    }


def collect_gpu_metrics() -> GpuMetrics:
    return parse_gpu_metrics(run_intel_gpu_top())
