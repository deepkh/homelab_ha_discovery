"""Read NVIDIA GPU metrics from nvidia-smi."""

from __future__ import annotations

import csv
import os
import subprocess

from homelab_ha_discovery.collectors.gpu_common import GpuMetrics, clamp_percent


def run_nvidia_smi() -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def parse_gpu_metrics(nvidia_smi_output: str) -> GpuMetrics:
    metrics: GpuMetrics = {}

    for row in csv.reader(nvidia_smi_output.splitlines(), skipinitialspace=True):
        fields = [field.strip() for field in row]
        if not fields or all(not field for field in fields):
            continue

        if len(fields) == 5:
            gpu_key = f"gpu{len(metrics)}"
            metric_fields = fields
        elif len(fields) == 6:
            gpu_index = int(fields[0])
            if gpu_index < 0:
                raise ValueError(f"Invalid NVIDIA GPU index: {gpu_index}")
            gpu_key = f"gpu{gpu_index}"
            metric_fields = fields[1:]
        else:
            raise ValueError(
                f"Unexpected nvidia-smi output line: {', '.join(fields)}"
            )

        card_name = metric_fields[0]
        if not card_name:
            raise ValueError("Missing NVIDIA GPU card name")

        gpu_usage = float(metric_fields[1])
        memory_used = float(metric_fields[2])
        memory_total = float(metric_fields[3])
        temperature = float(metric_fields[4])
        if memory_total <= 0:
            raise ValueError(f"Invalid NVIDIA GPU memory total: {memory_total}")
        if gpu_key in metrics:
            raise ValueError(
                f"Duplicate NVIDIA GPU index in nvidia-smi output: {gpu_key}"
            )

        metrics[gpu_key] = {
            "GPU Card Name": card_name,
            "GPU Usages": clamp_percent(gpu_usage),
            "Memory Usage": clamp_percent((memory_used / memory_total) * 100.0),
            "Temperature": round(temperature),
        }

    if not metrics:
        raise ValueError("Could not find GPU metrics in nvidia-smi output")

    return metrics


def collect_gpu_metrics() -> GpuMetrics:
    return parse_gpu_metrics(run_nvidia_smi())
