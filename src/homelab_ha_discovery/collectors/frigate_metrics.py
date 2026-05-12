"""Read Frigate metrics from the Prometheus text endpoint."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import socket
import urllib.error
import urllib.request


DEFAULT_FRIGATE_METRICS_URL = "http://127.0.0.1:5000/api/metrics"
DEFAULT_FRIGATE_HTTP_TIMEOUT_SECONDS = 5.0
BYTES_PER_GIGABYTE = 1000_000_000.0
METRIC_DECIMAL_PLACES = 3
SYSTEM_PID = "frigate.full_system"

FrigateMetricValue = float
FrigateSectionMetrics = dict[str, FrigateMetricValue]
FrigateMetrics = dict[str, object]

METRIC_SAMPLE_RE = re.compile(
    r"^(?P<name>[A-Za-z_:][A-Za-z0-9_:]*)"
    r"(?:\{(?P<labels>.*)\})?"
    r"\s+"
    r"(?P<value>[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|Inf|NaN))"
    r"(?:\s+[+-]?\d+(?:\.\d+)?)?"
    r"\s*$"
)
LABEL_PAIR_RE = re.compile(
    r'\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*"(?P<value>(?:\\.|[^"\\])*)"\s*(?:,|$)'
)


@dataclass(frozen=True)
class PrometheusSample:
    name: str
    labels: dict[str, str]
    value: float


PrometheusFamilies = dict[str, list[PrometheusSample]]


CAMERA_METRICS = {
    "frigate_camera_fps": "Camera FPS",
    "frigate_process_fps": "Process FPS",
    "frigate_skipped_fps": "Skipped FPS",
    "frigate_detection_fps": "Detection FPS",
}
DETECTOR_METRICS = {
    "frigate_detector_inference_speed_seconds": "Inference Speed",
}
SYSTEM_METRICS = {
    "frigate_cpu_usage_percent": "CPU Usage",
    "frigate_mem_usage_percent": "Memory Usage",
}
GPU_METRICS = {
    "frigate_gpu_usage_percent": "GPU Usage",
    "frigate_gpu_mem_usage_percent": "Memory Usage",
}
STORAGE_METRICS = {
    "frigate_storage_free_bytes": "Free GB",
    "frigate_storage_used_bytes": "Used GB",
}


def decode_label_value(value: str) -> str:
    decoded: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            decoded.append(char)
            index += 1
            continue

        index += 1
        if index >= len(value):
            raise ValueError(f"invalid Prometheus label escape: {value!r}")
        escaped = value[index]
        if escaped == "n":
            decoded.append("\n")
        elif escaped in {'"', "\\"}:
            decoded.append(escaped)
        else:
            decoded.append(escaped)
        index += 1
    return "".join(decoded)


def parse_prometheus_labels(label_text: str | None) -> dict[str, str]:
    if label_text is None or not label_text.strip():
        return {}

    labels: dict[str, str] = {}
    position = 0
    while position < len(label_text):
        match = LABEL_PAIR_RE.match(label_text, position)
        if not match:
            raise ValueError(f"invalid Prometheus labels: {label_text!r}")
        key = match.group("key")
        if key in labels:
            raise ValueError(f"duplicate Prometheus label {key!r}")
        labels[key] = decode_label_value(match.group("value"))
        position = match.end()
    return labels


def parse_prometheus_text(metrics_text: str) -> PrometheusFamilies:
    families: PrometheusFamilies = {}
    for line_number, raw_line in enumerate(metrics_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = METRIC_SAMPLE_RE.fullmatch(line)
        if not match:
            raise ValueError(
                f"invalid Prometheus metric line {line_number}: {raw_line!r}"
            )

        try:
            value = float(match.group("value"))
        except ValueError as exc:
            raise ValueError(
                f"invalid Prometheus metric value on line {line_number}: {raw_line!r}"
            ) from exc
        if not math.isfinite(value):
            raise ValueError(
                f"invalid Prometheus metric value on line {line_number}: {raw_line!r}"
            )

        sample = PrometheusSample(
            name=match.group("name"),
            labels=parse_prometheus_labels(match.group("labels")),
            value=value,
        )
        families.setdefault(sample.name, []).append(sample)
    return families


def require_family(
    families: PrometheusFamilies,
    metric_name: str,
) -> list[PrometheusSample]:
    samples = families.get(metric_name)
    if not samples:
        raise ValueError(f"missing Frigate metric family: {metric_name}")
    return samples


def round_metric(value: float) -> float:
    return round(value, METRIC_DECIMAL_PLACES)


def sample_label_value(
    sample: PrometheusSample,
    label_names: tuple[str, ...],
    metric_name: str,
    fallback: str | None = None,
) -> str:
    for label_name in label_names:
        value = sample.labels.get(label_name)
        if value is not None and value.strip():
            return value
    if fallback is not None:
        return fallback
    raise ValueError(
        f"Frigate metric {metric_name} is missing one of labels: "
        + ", ".join(label_names)
    )


def metric_values_by_label(
    families: PrometheusFamilies,
    metric_name: str,
    label_names: tuple[str, ...],
    fallback_prefix: str | None = None,
) -> dict[str, float]:
    values: dict[str, float] = {}
    for index, sample in enumerate(require_family(families, metric_name)):
        fallback = f"{fallback_prefix}{index}" if fallback_prefix is not None else None
        label = sample_label_value(
            sample,
            label_names,
            metric_name,
            fallback=fallback,
        )
        values[label] = round_metric(sample.value)
    return values


def metric_values_by_system_pid(
    families: PrometheusFamilies,
    metric_name: str,
) -> float:
    value: float | None = None
    for sample in require_family(families, metric_name):
        if sample.labels.get("pid") == SYSTEM_PID:
            value = round_metric(sample.value)
    if value is None:
        raise ValueError(
            f"missing Frigate metric {metric_name} with pid={SYSTEM_PID!r}"
        )
    return value


def require_payload_metrics(
    grouped_metrics: dict[str, FrigateSectionMetrics],
    section_name: str,
    required_metrics: tuple[str, ...],
) -> None:
    if not grouped_metrics:
        raise ValueError(f"missing Frigate {section_name} metrics")
    for label, metrics in grouped_metrics.items():
        missing = [
            metric_name
            for metric_name in required_metrics
            if metric_name not in metrics
        ]
        if missing:
            raise ValueError(
                f"missing Frigate {section_name} metric(s) for {label!r}: "
                + ", ".join(missing)
            )


def parse_grouped_metrics(
    families: PrometheusFamilies,
    metric_map: dict[str, str],
    label_names: tuple[str, ...],
    section_name: str,
    fallback_prefix: str | None = None,
) -> dict[str, FrigateSectionMetrics]:
    grouped_metrics: dict[str, FrigateSectionMetrics] = {}
    for metric_name, payload_metric_name in metric_map.items():
        values = metric_values_by_label(
            families,
            metric_name,
            label_names,
            fallback_prefix=fallback_prefix,
        )
        for label, value in values.items():
            grouped_metrics.setdefault(label, {})[payload_metric_name] = value

    require_payload_metrics(
        grouped_metrics,
        section_name,
        tuple(metric_map.values()),
    )
    return grouped_metrics


def parse_storage_metrics(
    families: PrometheusFamilies,
) -> dict[str, FrigateSectionMetrics]:
    storage_metrics: dict[str, FrigateSectionMetrics] = {}
    for metric_name, payload_metric_name in STORAGE_METRICS.items():
        for storage_label, byte_value in metric_values_by_label(
            families,
            metric_name,
            ("storage",),
        ).items():
            storage_metrics.setdefault(storage_label, {})[payload_metric_name] = round(
                byte_value / BYTES_PER_GIGABYTE,
                METRIC_DECIMAL_PLACES,
            )

    require_payload_metrics(
        storage_metrics,
        "storage",
        tuple(STORAGE_METRICS.values()),
    )
    return storage_metrics


def parse_frigate_metrics(metrics_text: str) -> FrigateMetrics:
    families = parse_prometheus_text(metrics_text)

    system = {
        payload_metric_name: metric_values_by_system_pid(families, metric_name)
        for metric_name, payload_metric_name in SYSTEM_METRICS.items()
    }
    cameras = parse_grouped_metrics(
        families,
        CAMERA_METRICS,
        ("camera_name", "camera"),
        "camera",
    )
    detectors = parse_grouped_metrics(
        families,
        DETECTOR_METRICS,
        ("name", "detector"),
        "detector",
    )
    gpus = parse_grouped_metrics(
        families,
        GPU_METRICS,
        ("gpu_name", "gpu", "name"),
        "GPU",
        fallback_prefix="gpu",
    )
    storage = parse_storage_metrics(families)

    return {
        "system": system,
        "cameras": cameras,
        "detectors": detectors,
        "gpus": gpus,
        "storage": storage,
    }


def fetch_frigate_metrics_text(
    url: str = DEFAULT_FRIGATE_METRICS_URL,
    timeout: float = DEFAULT_FRIGATE_HTTP_TIMEOUT_SECONDS,
) -> str:
    if not url.strip():
        raise ValueError("Frigate metrics URL is required")
    request = urllib.request.Request(
        url,
        headers={"Accept": "text/plain"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                raise RuntimeError(
                    f"Frigate metrics request failed: HTTP status {status}"
                )
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Frigate metrics request failed: HTTP status {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Frigate metrics request failed: {exc.reason}") from exc
    except socket.timeout as exc:
        raise RuntimeError(
            f"Frigate metrics request timed out after {timeout:g} seconds"
        ) from exc


def read_frigate_metrics(
    url: str = DEFAULT_FRIGATE_METRICS_URL,
    timeout: float = DEFAULT_FRIGATE_HTTP_TIMEOUT_SECONDS,
) -> FrigateMetrics:
    return parse_frigate_metrics(fetch_frigate_metrics_text(url, timeout=timeout))
