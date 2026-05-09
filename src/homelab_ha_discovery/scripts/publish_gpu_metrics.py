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
from homelab_ha_discovery.discovery import MetricIdentity, mqtt_topic_prefix
from homelab_ha_discovery.env import load_env_files
from homelab_ha_discovery.mqtt import publish_mqtt


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)


def gpu_metrics_identity(host: str) -> MetricIdentity:
    return MetricIdentity(
        host=host,
        component="gpu",
        metric="metrics",
        state_topic_override=f"{mqtt_topic_prefix()}/gpu/usages/{host}",
    )


def gpu_metrics_client_id(host: str) -> str:
    if not host:
        raise ValueError("host is required")
    return f"homelab-ha-discovery_{host}_gpu_metrics"


def publish_gpu_metrics(
    env_files: tuple[str, ...],
    host: str,
    default_mqtt_topic: str | None = None,
) -> int:
    try:
        load_env_files(env_files)
        identity = gpu_metrics_identity(host)
        payload = json.dumps(parse_gpu_metrics(run_nvidia_smi()), separators=(",", ":"))
        mqtt_topic = os.environ.get("MQTT_TOPIC", default_mqtt_topic or identity.state_topic)
        publish_mqtt(mqtt_topic, payload, default_client_id=gpu_metrics_client_id(host))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    args = parser.parse_args(argv)
    return publish_gpu_metrics(DEFAULT_ENV_FILES, args.host)


if __name__ == "__main__":
    raise SystemExit(main())
