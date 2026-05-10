"""Read NVMe SMART metrics from smartctl."""

from __future__ import annotations

import os
import re
import subprocess


NvmeSmartMetricValue = int | float
NvmeSmartMetrics = dict[str, NvmeSmartMetricValue]

NVME_SMART_INTEGER_FIELD_MAPPINGS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("Critical Warning",), "Critical Warning"),
    (("Media and Data Integrity Errors",), "Media and Data Integrity Errors"),
    (("Available Spare",), "Available Spare"),
    (("Percentage Used",), "Percentage Used"),
    (
        ("Critical Comp. Temperature Time", "Critical Temperature Time"),
        "Critical Temperature Time",
    ),
    (("Temperature",), "temperature_c"),
    (("Power On Hours",), "power_on_hours"),
)
NVME_SMART_FIELDS_BY_LABEL: dict[str, str] = {
    label: metric_name
    for labels, metric_name in NVME_SMART_INTEGER_FIELD_MAPPINGS
    for label in labels
}
RAW_INTEGER_RE = re.compile(r"^[+-]?(?:0[xX][0-9a-fA-F]+|\d[\d,]*)")
DATA_WRITTEN_LABEL = "Data Units Written"
DATA_WRITTEN_METRIC = "data_written_tb"
NVME_SMART_METRIC_ORDER = (
    "Critical Warning",
    "Media and Data Integrity Errors",
    "Available Spare",
    "Percentage Used",
    "Critical Temperature Time",
    "temperature_c",
    DATA_WRITTEN_METRIC,
    "power_on_hours",
)
DATA_SIZE_RE = re.compile(
    r"\[\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?i?B)\s*\]",
    re.IGNORECASE,
)
DATA_SIZE_FACTORS_TO_TB = {
    "B": 1 / 1_000_000_000_000,
    "KB": 1 / 1_000_000_000,
    "KIB": 1024 / 1_000_000_000_000,
    "MB": 1 / 1_000_000,
    "MIB": 1024**2 / 1_000_000_000_000,
    "GB": 1 / 1_000,
    "GIB": 1024**3 / 1_000_000_000_000,
    "TB": 1,
    "TIB": 1024**4 / 1_000_000_000_000,
    "PB": 1_000,
    "PIB": 1024**5 / 1_000_000_000_000,
    "EB": 1_000_000,
    "EIB": 1024**6 / 1_000_000_000_000,
}
NVME_DATA_UNIT_BYTES = 512_000


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


def parse_nvme_smart_metrics(smartctl_output: str) -> NvmeSmartMetrics:
    metrics: NvmeSmartMetrics = {}

    for line in smartctl_output.splitlines():
        label, separator, raw_value = line.partition(":")
        if not separator:
            continue

        clean_label = label.strip()
        if clean_label == DATA_WRITTEN_LABEL:
            metrics[DATA_WRITTEN_METRIC] = parse_data_written_tb(raw_value.strip())
            continue

        metric_name = NVME_SMART_FIELDS_BY_LABEL.get(clean_label)
        if metric_name is None:
            continue
        raw_match = RAW_INTEGER_RE.match(raw_value.strip())
        if not raw_match:
            raise ValueError(
                f"Could not parse NVMe SMART value for {metric_name}: "
                f"{raw_value.strip()!r}"
            )

        metrics[metric_name] = int(raw_match.group(0).replace(",", ""), 0)

    missing_metrics = [
        metric_name
        for _, metric_name in NVME_SMART_INTEGER_FIELD_MAPPINGS
        if metric_name not in metrics
    ]
    if DATA_WRITTEN_METRIC not in metrics:
        missing_metrics.append(DATA_WRITTEN_METRIC)
    if missing_metrics:
        raise ValueError(
            "Could not find required NVMe SMART metric(s): "
            + ", ".join(missing_metrics)
        )

    return {metric_name: metrics[metric_name] for metric_name in NVME_SMART_METRIC_ORDER}


def parse_data_written_tb(raw_value: str) -> float:
    size_match = DATA_SIZE_RE.search(raw_value)
    if size_match:
        value = float(size_match.group(1))
        unit = size_match.group(2).upper()
        return round(value * DATA_SIZE_FACTORS_TO_TB[unit], 2)

    raw_match = RAW_INTEGER_RE.match(raw_value)
    if not raw_match:
        raise ValueError(
            f"Could not parse NVMe SMART value for {DATA_WRITTEN_METRIC}: "
            f"{raw_value!r}"
        )

    data_units = int(raw_match.group(0).replace(",", ""), 0)
    return round(data_units * NVME_DATA_UNIT_BYTES / 1_000_000_000_000, 2)
