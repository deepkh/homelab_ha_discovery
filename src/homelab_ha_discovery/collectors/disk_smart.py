"""Read disk SMART metrics from smartctl."""

from __future__ import annotations

import os
import re
import subprocess


SmartMetrics = dict[str, int]

SMART_ATTRIBUTE_MAPPINGS: tuple[tuple[int, str, str], ...] = (
    (9, "Power_On_Hours", "Power On Hours"),
    (194, "Temperature_Celsius", "Temperature"),
    (5, "Reallocated_Sector_Ct", "Reallocated Sectors"),
    (197, "Current_Pending_Sector", "Pending Sectors"),
)
SMART_ATTRIBUTES_BY_ID: dict[int, tuple[str, str]] = {
    attribute_id: (attribute_name, metric_name)
    for attribute_id, attribute_name, metric_name in SMART_ATTRIBUTE_MAPPINGS
}
RAW_INTEGER_RE = re.compile(r"^[+-]?\d+")


def run_smartctl(dev: str) -> str:
    if not dev:
        raise ValueError("dev is required")

    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ["sudo", "smartctl", "-a", dev],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def parse_smart_metrics(smartctl_output: str) -> SmartMetrics:
    metrics: SmartMetrics = {}

    for line in smartctl_output.splitlines():
        fields = line.split(None, 9)
        if len(fields) < 10:
            continue

        try:
            attribute_id = int(fields[0])
        except ValueError:
            continue

        if attribute_id not in SMART_ATTRIBUTES_BY_ID:
            continue

        _, metric_name = SMART_ATTRIBUTES_BY_ID[attribute_id]
        raw_value = fields[9].strip()
        raw_match = RAW_INTEGER_RE.match(raw_value)
        if not raw_match:
            raise ValueError(
                f"Could not parse SMART raw value for {metric_name}: {raw_value!r}"
            )

        metrics[metric_name] = int(raw_match.group(0))

    missing_metrics = [
        metric_name
        for _, _, metric_name in SMART_ATTRIBUTE_MAPPINGS
        if metric_name not in metrics
    ]
    if missing_metrics:
        raise ValueError(
            "Could not find required SMART metric(s): "
            + ", ".join(missing_metrics)
        )

    return {
        metric_name: metrics[metric_name]
        for _, _, metric_name in SMART_ATTRIBUTE_MAPPINGS
    }
