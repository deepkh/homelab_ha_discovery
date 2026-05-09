"""Publish NVIDIA GPU metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.gpu_nvidia import parse_gpu_metrics, run_nvidia_smi
from homelab_ha_discovery.discovery import (
    MetricIdentity,
    mqtt_topic_prefix,
    sensor_discovery_config,
)
from homelab_ha_discovery.env import load_env_files
from homelab_ha_discovery.mqtt import publish_mqtt


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)


def gpu_state_topic(device: str) -> str:
    return f"{mqtt_topic_prefix()}/gpu/usages/{device}"


def gpu_metrics_identity(
    device: str,
    state_topic_override: str | None = None,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component="gpu",
        metric="metrics",
        state_topic_override=state_topic_override or gpu_state_topic(device),
    )


def gpu_usage_identity(device: str, state_topic: str) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component="gpu",
        metric="usage",
        state_topic_override=state_topic,
    )


def gpu_memory_usage_identity(device: str, state_topic: str) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component="gpu",
        metric="memory_usage",
        state_topic_override=state_topic,
    )


def gpu_metrics_client_id(device: str) -> str:
    if not device:
        raise ValueError("device is required")
    return f"homelab-ha-discovery_{device}_gpu_metrics"


def publish_gpu_discovery(device: str, state_topic: str) -> None:
    configs = (
        (
            gpu_usage_identity(device, state_topic),
            f"{device} GPU Usage",
            "{{ value_json['GPU Usages'] }}",
        ),
        (
            gpu_memory_usage_identity(device, state_topic),
            f"{device} GPU Memory Usage",
            "{{ value_json['Memory Usage'] }}",
        ),
    )
    for identity, name, value_template in configs:
        payload = json.dumps(
            sensor_discovery_config(
                identity,
                name=name,
                unit_of_measurement="%",
                state_class="measurement",
                value_template=value_template,
            ),
            separators=(",", ":"),
        )
        publish_mqtt(
            identity.discovery_topic,
            payload,
            default_client_id=gpu_metrics_client_id(device),
            retain=True,
        )


def publish_gpu_metrics(
    env_files: tuple[str, ...],
    device: str,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
) -> int:
    try:
        load_env_files(env_files)
        identity = gpu_metrics_identity(device)
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic or identity.state_topic,
        )
        if not publisher_only:
            publish_gpu_discovery(device, mqtt_topic)

        payload = json.dumps(parse_gpu_metrics(run_nvidia_smi()), separators=(",", ":"))
        publish_mqtt(mqtt_topic, payload, default_client_id=gpu_metrics_client_id(device))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device")
    parser.add_argument("--host", dest="device", help=argparse.SUPPRESS)
    parser.add_argument(
        "--publisher-only",
        action="store_true",
        help="Publish metric state without Home Assistant discovery config.",
    )
    args = parser.parse_args(argv)
    if not args.device:
        parser.error("the following arguments are required: --device")
    return publish_gpu_metrics(
        DEFAULT_ENV_FILES,
        args.device,
        publisher_only=args.publisher_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
