"""Read Linux network throughput metrics from psutil."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time

import psutil


NetworkMetrics = dict[str, float]
BITS_PER_MEGABIT = 1000_000.0
NETWORK_SPEED_DECIMAL_PLACES = 3


@dataclass(frozen=True)
class NetworkCounterSample:
    bytes_recv: int
    bytes_sent: int
    timestamp: float


def read_network_counter_sample(interface: str) -> NetworkCounterSample:
    if not interface:
        raise ValueError("network interface is required")

    counters_by_interface = psutil.net_io_counters(pernic=True)
    counters = counters_by_interface.get(interface)
    if counters is None:
        interfaces = ", ".join(sorted(counters_by_interface)) or "none"
        raise ValueError(
            f"Network interface {interface!r} not found; "
            f"available interfaces: {interfaces}"
        )

    return NetworkCounterSample(
        bytes_recv=int(counters.bytes_recv),
        bytes_sent=int(counters.bytes_sent),
        timestamp=time.monotonic(),
    )


def calculate_network_speed_metrics(
    previous: NetworkCounterSample,
    current: NetworkCounterSample,
) -> NetworkMetrics:
    elapsed_seconds = current.timestamp - previous.timestamp
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError("elapsed time between network samples must be greater than 0")

    bytes_recv_delta = current.bytes_recv - previous.bytes_recv
    bytes_sent_delta = current.bytes_sent - previous.bytes_sent
    if bytes_recv_delta < 0 or bytes_sent_delta < 0:
        raise ValueError("network byte counters decreased unexpectedly")

    return {
        "Download Speed": round(
            bytes_recv_delta * 8 / elapsed_seconds / BITS_PER_MEGABIT,
            NETWORK_SPEED_DECIMAL_PLACES,
        ),
        "Upload Speed": round(
            bytes_sent_delta * 8 / elapsed_seconds / BITS_PER_MEGABIT,
            NETWORK_SPEED_DECIMAL_PLACES,
        ),
    }
