"""Publish GPU metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.gpu_amd_rocm import (
    collect_gpu_metrics as collect_amd_rocm_gpu_metrics,
)
from homelab_ha_discovery.collectors.gpu_common import GpuMetrics
from homelab_ha_discovery.collectors.gpu_intel_qsv import (
    collect_gpu_metrics as collect_intel_qsv_gpu_metrics,
)
from homelab_ha_discovery.collectors.gpu_nvidia import (
    collect_gpu_metrics as collect_nvidia_gpu_metrics,
)
from homelab_ha_discovery.discovery import (
    MetricIdentity,
    effective_expire_after,
    mqtt_topic_prefix,
    sensor_discovery_config,
    validate_expire_after_seconds,
)
from homelab_ha_discovery.env import load_env_files
from homelab_ha_discovery.mqtt import MqttMessage, MqttPublisher, publish_mqtt_many
from homelab_ha_discovery.scripts.timer import (
    run_publish_timer,
    validate_timer_seconds,
)


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)
DEFAULT_GPU_COLLECTOR = "nvidia"
GPU_COLLECTOR_ALIASES = {
    "nvidia": "nvidia",
    "amd": "amd_rocm",
    "rocm": "amd_rocm",
    "amd_rocm": "amd_rocm",
    "amd-rocm": "amd_rocm",
    "intel": "intel_qsv",
    "qsv": "intel_qsv",
    "intel_qsv": "intel_qsv",
    "intel-qsv": "intel_qsv",
}
GPU_COLLECTOR_LABELS = {
    "nvidia": "",
    "amd_rocm": "AMD ROCm",
    "intel_qsv": "Intel QSV",
}
INTEL_QSV_DISCOVERY_CONFIGS = (
    ("video_busy", "Video Busy", "Video Engine Busy", "%", None),
    (
        "video_enhance_busy",
        "VideoEnhance Busy",
        "VideoEnhance Engine Busy",
        "%",
        None,
    ),
    ("render_busy", "Render/3D Busy", "Render/3D Engine Busy", "%", None),
    ("blitter_busy", "Blitter Busy", "Blitter Engine Busy", "%", None),
    ("compute_busy", "Compute Busy", "Compute Engine Busy", "%", None),
    ("qsv_active", "QSV Active", "QSV Active", None, None),
    ("qsv_available", "QSV Available", "QSV Available", None, None),
)


def normalize_gpu_collector(collector: str | None) -> str:
    normalized = (collector or DEFAULT_GPU_COLLECTOR).strip().lower().replace("-", "_")
    if normalized not in GPU_COLLECTOR_ALIASES:
        choices = ", ".join(sorted(GPU_COLLECTOR_ALIASES))
        raise ValueError(
            f"unsupported GPU collector: {collector}; expected one of {choices}"
        )
    return GPU_COLLECTOR_ALIASES[normalized]


def collect_gpu_metrics(collector: str) -> GpuMetrics:
    collector = normalize_gpu_collector(collector)
    if collector == "nvidia":
        return collect_nvidia_gpu_metrics()
    if collector == "amd_rocm":
        return collect_amd_rocm_gpu_metrics()
    if collector == "intel_qsv":
        return collect_intel_qsv_gpu_metrics()
    raise ValueError(f"unsupported GPU collector: {collector}")


def gpu_key(gpu_index: int) -> str:
    if gpu_index < 0:
        raise ValueError("GPU index must be zero or greater")
    return f"gpu{gpu_index}"


def normalize_gpu_indexes(
    gpu_index: int | None = None,
    gpu_indexes: tuple[int, ...] | None = None,
) -> tuple[int, ...] | None:
    if gpu_index is not None and gpu_indexes is not None:
        raise ValueError("gpu_index and gpu_indexes cannot both be set")
    if gpu_index is not None:
        gpu_indexes = (gpu_index,)
    if gpu_indexes is None:
        return None
    if not gpu_indexes:
        raise ValueError("gpu_indexes must not be empty")

    normalized: list[int] = []
    for index in gpu_indexes:
        if index < 0:
            raise ValueError("GPU index must be zero or greater")
        if index not in normalized:
            normalized.append(index)
    return tuple(normalized)


def gpu_state_topic(
    device: str,
    gpu_index: int | None = None,
    *,
    collector: str = DEFAULT_GPU_COLLECTOR,
    gpu_indexes: tuple[int, ...] | None = None,
) -> str:
    collector = normalize_gpu_collector(collector)
    indexes = normalize_gpu_indexes(gpu_index, gpu_indexes)
    if collector == "nvidia":
        topic = f"{mqtt_topic_prefix()}/gpu/usages/{device}"
    else:
        topic = f"{mqtt_topic_prefix()}/gpu/{collector}/usages/{device}"
    if indexes is None or len(indexes) != 1:
        return topic
    return f"{topic}/{gpu_key(indexes[0])}"


def gpu_metrics_identity(
    device: str,
    gpu_index: int | None = None,
    state_topic_override: str | None = None,
    *,
    collector: str = DEFAULT_GPU_COLLECTOR,
    gpu_indexes: tuple[int, ...] | None = None,
) -> MetricIdentity:
    collector = normalize_gpu_collector(collector)
    component = "gpu" if collector == "nvidia" else f"{collector}_gpu"
    return MetricIdentity(
        host=device,
        component=component,
        metric="metrics",
        state_topic_override=state_topic_override
        or gpu_state_topic(
            device,
            gpu_index,
            collector=collector,
            gpu_indexes=gpu_indexes,
        ),
    )


def gpu_metric_identity(
    device: str,
    key: str,
    metric: str,
    state_topic: str,
    *,
    collector: str = DEFAULT_GPU_COLLECTOR,
) -> MetricIdentity:
    collector = normalize_gpu_collector(collector)
    component = key if collector == "nvidia" else f"{collector}_{key}"
    return MetricIdentity(
        host=device,
        component=component,
        metric=metric,
        state_topic_override=state_topic,
    )


def select_gpu_metrics(
    metrics: GpuMetrics,
    gpu_index: int | None = None,
    gpu_indexes: tuple[int, ...] | None = None,
) -> GpuMetrics:
    indexes = normalize_gpu_indexes(gpu_index, gpu_indexes)
    if indexes is None:
        return metrics

    selected: GpuMetrics = {}
    for index in indexes:
        key = gpu_key(index)
        if key not in metrics:
            raise ValueError(
                f"GPU index {index} is out of range; detected {len(metrics)} GPU(s)"
            )
        selected[key] = metrics[key]
    return selected


def gpu_metrics_client_id(
    device: str,
    collector: str = DEFAULT_GPU_COLLECTOR,
) -> str:
    if not device:
        raise ValueError("device is required")
    collector = normalize_gpu_collector(collector)
    if collector == "nvidia":
        return f"homelab-ha-discovery_{device}_gpu_metrics"
    return f"homelab-ha-discovery_{device}_{collector}_gpu_metrics"


def publish_gpu_discovery(
    device: str,
    state_topic: str,
    metrics: GpuMetrics,
    expire_after: float | None = None,
    collector: str = DEFAULT_GPU_COLLECTOR,
) -> None:
    publish_mqtt_many(
        gpu_discovery_messages(
            device,
            state_topic,
            metrics,
            expire_after=expire_after,
            collector=collector,
        ),
        default_client_id=gpu_metrics_client_id(device, collector),
    )


def gpu_metric_name(device: str, collector: str, key: str, label: str) -> str:
    collector = normalize_gpu_collector(collector)
    collector_label = GPU_COLLECTOR_LABELS[collector]
    if collector_label:
        return f"{device} {collector_label} {key.upper()} {label}"
    return f"{device} {key.upper()} {label}"


def gpu_discovery_messages(
    device: str,
    state_topic: str,
    metrics: GpuMetrics,
    expire_after: float | None = None,
    collector: str = DEFAULT_GPU_COLLECTOR,
) -> list[MqttMessage]:
    collector = normalize_gpu_collector(collector)
    messages: list[MqttMessage] = []
    for key in metrics:
        if collector == "intel_qsv":
            configs = intel_qsv_discovery_configs(device, key, state_topic)
        else:
            configs = (
                (
                    gpu_metric_identity(
                        device,
                        key,
                        "usage",
                        state_topic,
                        collector=collector,
                    ),
                    gpu_metric_name(device, collector, key, "Usage"),
                    "%",
                    None,
                    f"{{{{ value_json['{key}']['GPU Usages'] }}}}",
                ),
                (
                    gpu_metric_identity(
                        device,
                        key,
                        "memory_usage",
                        state_topic,
                        collector=collector,
                    ),
                    gpu_metric_name(device, collector, key, "Memory Usage"),
                    "%",
                    None,
                    f"{{{{ value_json['{key}']['Memory Usage'] }}}}",
                ),
                (
                    gpu_metric_identity(
                        device,
                        key,
                        "temperature",
                        state_topic,
                        collector=collector,
                    ),
                    gpu_metric_name(device, collector, key, "Temperature"),
                    "°C",
                    "temperature",
                    f"{{{{ value_json['{key}']['Temperature'] }}}}",
                ),
            )
        for (
            identity,
            name,
            unit_of_measurement,
            device_class,
            value_template,
        ) in configs:
            payload = json.dumps(
                sensor_discovery_config(
                    identity,
                    name=name,
                    unit_of_measurement=unit_of_measurement,
                    device_class=device_class,
                    state_class="measurement",
                    value_template=value_template,
                    expire_after=expire_after,
                ),
                separators=(",", ":"),
            )
            messages.append((identity.discovery_topic, payload, True))
    return messages


def intel_qsv_discovery_configs(
    device: str,
    key: str,
    state_topic: str,
) -> tuple[tuple[MetricIdentity, str, str | None, str | None, str], ...]:
    configs: list[tuple[MetricIdentity, str, str | None, str | None, str]] = []
    for config in INTEL_QSV_DISCOVERY_CONFIGS:
        metric, payload_key, label, unit_of_measurement, device_class = config
        if metric in {"qsv_active", "qsv_available"}:
            value_template = (
                f"{{{{ 1 if value_json['{key}']['{payload_key}'] else 0 }}}}"
            )
        else:
            value_template = f"{{{{ value_json['{key}']['{payload_key}'] }}}}"

        configs.append(
            (
                gpu_metric_identity(
                    device,
                    key,
                    metric,
                    state_topic,
                    collector="intel_qsv",
                ),
                gpu_metric_name(device, "intel_qsv", key, label),
                unit_of_measurement,
                device_class,
                value_template,
            )
        )
    return tuple(configs)


def publish_gpu_metrics(
    env_files: tuple[str, ...],
    device: str,
    default_mqtt_topic: str | None = None,
    gpu_index: int | None = None,
    gpu_indexes: tuple[int, ...] | None = None,
    collector: str = DEFAULT_GPU_COLLECTOR,
    publisher_only: bool = False,
    expire_after: float | None = None,
    mqtt_publisher: MqttPublisher | None = None,
) -> int:
    try:
        collector = normalize_gpu_collector(collector)
        indexes = normalize_gpu_indexes(gpu_index, gpu_indexes)
        if mqtt_publisher is None:
            load_env_files(env_files)
        identity = gpu_metrics_identity(
            device,
            collector=collector,
            gpu_indexes=indexes,
        )
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic or identity.state_topic,
        )
        metrics = select_gpu_metrics(
            collect_gpu_metrics(collector),
            gpu_indexes=indexes,
        )
        mqtt_messages: list[MqttMessage] = []
        if not publisher_only:
            mqtt_messages.extend(
                gpu_discovery_messages(
                    device,
                    mqtt_topic,
                    metrics,
                    expire_after=expire_after,
                    collector=collector,
                )
            )

        payload = json.dumps(metrics, separators=(",", ":"))
        mqtt_messages.append((mqtt_topic, payload, False))
        if mqtt_publisher is None:
            publish_mqtt_many(
                mqtt_messages,
                default_client_id=gpu_metrics_client_id(device, collector),
            )
        else:
            mqtt_publisher.publish_many(mqtt_messages)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ha-device-id",
        dest="device",
        help="Stable Home Assistant/MQTT device identity.",
    )
    parser.add_argument(
        "--collector",
        default=DEFAULT_GPU_COLLECTOR,
        help=(
            "GPU collector backend: nvidia, amd_rocm, or intel_qsv. "
            "Default: nvidia."
        ),
    )
    parser.add_argument(
        "--gpu",
        action="append",
        dest="gpus",
        type=int,
        metavar="INDEX",
        help="Publish only a zero-based GPU index. May be repeated.",
    )
    parser.add_argument(
        "--publisher-only",
        action="store_true",
        help="Publish metric state without Home Assistant discovery config.",
    )
    parser.add_argument(
        "--expire-after",
        type=float,
        metavar="SECONDS",
        help=(
            "Set Home Assistant discovery expire_after. In timer mode the "
            "default is timer*3. Use 0 to disable expiry."
        ),
    )
    parser.add_argument(
        "--timer",
        type=float,
        help="Publish continuously every SECONDS instead of exiting after one run.",
    )
    parser.add_argument(
        "--timer-publish-discovery-config",
        type=float,
        metavar="SECONDS",
        help=(
            "Republish Home Assistant discovery config every SECONDS during --timer "
            "runs."
        ),
    )
    args = parser.parse_args(argv)
    if not args.device:
        parser.error("the following arguments are required: --ha-device-id")
    try:
        collector = normalize_gpu_collector(args.collector)
    except ValueError as exc:
        parser.error(str(exc))
    gpu_indexes = tuple(args.gpus) if args.gpus is not None else None
    if gpu_indexes is not None:
        for index in gpu_indexes:
            if index < 0:
                parser.error("--gpu must be zero or greater")
    if args.timer_publish_discovery_config is not None and args.timer is None:
        parser.error("--timer-publish-discovery-config requires --timer")
    if args.timer_publish_discovery_config is not None and args.publisher_only:
        parser.error(
            "--timer-publish-discovery-config cannot be used with --publisher-only"
        )
    if not validate_timer_seconds(
        args.timer_publish_discovery_config,
        "--timer-publish-discovery-config",
    ):
        return 1
    if not validate_timer_seconds(args.timer, "--timer"):
        return 1
    if not validate_expire_after_seconds(args.expire_after):
        return 1

    expire_after = effective_expire_after(args.expire_after, args.timer)

    next_discovery_publish_at = 0.0 if not args.publisher_only else None

    def publish(mqtt_publisher: MqttPublisher | None = None) -> int:
        nonlocal next_discovery_publish_at
        publish_discovery = (
            next_discovery_publish_at is not None
            and time.monotonic() >= next_discovery_publish_at
        )
        result = publish_gpu_metrics(
            DEFAULT_ENV_FILES,
            args.device,
            gpu_indexes=gpu_indexes,
            collector=collector,
            publisher_only=not publish_discovery,
            expire_after=expire_after,
            mqtt_publisher=mqtt_publisher,
        )
        if result == 0 and publish_discovery:
            if args.timer_publish_discovery_config is None:
                next_discovery_publish_at = None
            else:
                next_discovery_publish_at = (
                    time.monotonic() + args.timer_publish_discovery_config
                )
        return result

    if args.timer is not None:
        try:
            load_env_files(DEFAULT_ENV_FILES)
            with MqttPublisher(
                default_client_id=gpu_metrics_client_id(args.device, collector),
            ) as mqtt_publisher:
                return run_publish_timer(args.timer, lambda: publish(mqtt_publisher))
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return run_publish_timer(args.timer, publish)


if __name__ == "__main__":
    raise SystemExit(main())
