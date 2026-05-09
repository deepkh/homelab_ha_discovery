"""Read NVIDIA GPU metrics from nvidia-smi."""

from __future__ import annotations

import os
import subprocess


def run_nvidia_smi() -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
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


def parse_gpu_metrics(nvidia_smi_output: str) -> dict[str, float]:
    gpu_usages: list[float] = []
    memory_usages: list[float] = []
    temperatures: list[int] = []

    for line in nvidia_smi_output.splitlines():
        line = line.strip()
        if not line:
            continue

        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 4:
            raise ValueError(f"Unexpected nvidia-smi output line: {line}")

        gpu_usage = float(fields[0])
        memory_used = float(fields[1])
        memory_total = float(fields[2])
        temperature = float(fields[3])
        if memory_total <= 0:
            raise ValueError(f"Invalid NVIDIA GPU memory total: {memory_total}")

        gpu_usages.append(clamp_percent(gpu_usage))
        memory_usages.append(clamp_percent((memory_used / memory_total) * 100.0))
        temperatures.append(round(temperature))

    if not gpu_usages:
        raise ValueError("Could not find GPU metrics in nvidia-smi output")

    return {
        "GPU Usages": clamp_percent(sum(gpu_usages) / len(gpu_usages)),
        "Memory Usage": clamp_percent(sum(memory_usages) / len(memory_usages)),
        "Temperature": max(temperatures),
    }
