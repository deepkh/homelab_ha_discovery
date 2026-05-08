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

from homelab_monitor.collectors.cpu_top import parse_cpu_usage, run_top
from homelab_monitor.discovery import MetricIdentity, mqtt_topic_prefix
from homelab_monitor.env import load_env_files
from homelab_monitor.mqtt import publish_mqtt


DEFAULT_ENV_FILES = (
    "/etc/homelab-mqtt-monitor/mqtt.env",
)


def cpu_usage_identity(host: str) -> MetricIdentity:
    return MetricIdentity(
        host=host,
        component="cpu",
        metric="usage",
        state_topic_override=f"{mqtt_topic_prefix()}/cpu/usages/{host}",
    )


def cpu_usage_client_id(host: str) -> str:
    if not host:
        raise ValueError("host is required")
    return f"homelab-mqtt-monitor_{host}_cpu_usage"


def publish_cpu_usage(
    env_files: tuple[str, ...],
    host: str,
    default_mqtt_topic: str | None = None,
) -> int:
    try:
        load_env_files(env_files)
        identity = cpu_usage_identity(host)
        cpu_usage = parse_cpu_usage(run_top())
        payload = json.dumps({"CPU Usages": cpu_usage}, separators=(",", ":"))
        mqtt_topic = os.environ.get("MQTT_TOPIC", default_mqtt_topic or identity.state_topic)
        publish_mqtt(mqtt_topic, payload, default_client_id=cpu_usage_client_id(host))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    args = parser.parse_args(argv)
    return publish_cpu_usage(DEFAULT_ENV_FILES, args.host)


if __name__ == "__main__":
    raise SystemExit(main())
