"""Publish CPU usage metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.cpu_top import parse_cpu_usage, run_top
from homelab_ha_discovery.discovery import MetricIdentity, mqtt_topic_prefix
from homelab_ha_discovery.env import load_env_files
from homelab_ha_discovery.mqtt import publish_mqtt


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)


def cpu_usage_identity(device: str) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component="cpu",
        metric="usage",
        state_topic_override=f"{mqtt_topic_prefix()}/cpu/usages/{device}",
    )


def cpu_usage_client_id(device: str) -> str:
    if not device:
        raise ValueError("device is required")
    return f"homelab-ha-discovery_{device}_cpu_usage"


def publish_cpu_usage(
    env_files: tuple[str, ...],
    device: str,
    default_mqtt_topic: str | None = None,
) -> int:
    try:
        load_env_files(env_files)
        identity = cpu_usage_identity(device)
        cpu_usage = parse_cpu_usage(run_top())
        payload = json.dumps({"CPU Usages": cpu_usage}, separators=(",", ":"))
        mqtt_topic = os.environ.get("MQTT_TOPIC", default_mqtt_topic or identity.state_topic)
        publish_mqtt(mqtt_topic, payload, default_client_id=cpu_usage_client_id(device))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device")
    parser.add_argument("--host", dest="device", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.device:
        parser.error("the following arguments are required: --device")
    return publish_cpu_usage(DEFAULT_ENV_FILES, args.device)


if __name__ == "__main__":
    raise SystemExit(main())
