"""Read NVIDIA GPU metrics from nvidia-smi."""

from __future__ import annotations

import csv
import os
import subprocess


GpuMetricValue = str | float | int
GpuMetrics = dict[str, dict[str, GpuMetricValue]]


def run_nvidia_smi() -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def clamp_percent(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def parse_gpu_metrics(nvidia_smi_output: str) -> GpuMetrics:
    metrics: GpuMetrics = {}

    for row in csv.reader(nvidia_smi_output.splitlines(), skipinitialspace=True):
        fields = [field.strip() for field in row]
        if not fields or all(not field for field in fields):
            continue

        if len(fields) != 5:
            raise ValueError(
                f"Unexpected nvidia-smi output line: {', '.join(fields)}"
            )

        card_name = fields[0]
        if not card_name:
            raise ValueError("Missing NVIDIA GPU card name")

        gpu_usage = float(fields[1])
        memory_used = float(fields[2])
        memory_total = float(fields[3])
        temperature = float(fields[4])
        if memory_total <= 0:
            raise ValueError(f"Invalid NVIDIA GPU memory total: {memory_total}")

        metrics[f"gpu{len(metrics)}"] = {
            "GPU Card Name": card_name,
            "GPU Usages": clamp_percent(gpu_usage),
            "Memory Usage": clamp_percent((memory_used / memory_total) * 100.0),
            "Temperature": round(temperature),
        }

    if not metrics:
        raise ValueError("Could not find GPU metrics in nvidia-smi output")

    return metrics
