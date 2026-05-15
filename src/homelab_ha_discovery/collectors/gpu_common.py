"""Shared GPU metric collector helpers."""

from __future__ import annotations


GpuMetricValue = str | float | int | bool | None
GpuMetrics = dict[str, dict[str, GpuMetricValue]]


def clamp_percent(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)
