"""Read CPU temperature from sensors."""

from __future__ import annotations

import os
import re
import subprocess


TEMPERATURE_LABELS = ("Package id 0", "Tctl", "Tdie", "CPU", "temp1")
TEMPERATURE_RE = re.compile(
    r"^\s*(?P<label>[^:]+):\s*"
    r"(?P<temperature>[+-]?\d+(?:\.\d+)?)\s*(?:\u00b0)?C\b"
)


def run_sensors() -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ["sensors"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def parse_cpu_temperature(sensors_output: str) -> float:
    temperatures: dict[str, float] = {}
    for line in sensors_output.splitlines():
        match = TEMPERATURE_RE.search(line)
        if not match:
            continue

        label = match.group("label").strip()
        if label in TEMPERATURE_LABELS and label not in temperatures:
            temperatures[label] = round(float(match.group("temperature")), 1)

    for label in TEMPERATURE_LABELS:
        if label in temperatures:
            return temperatures[label]

    raise ValueError("Could not find CPU temperature in sensors output")
