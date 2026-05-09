"""Publish CPU usage metrics."""

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

from homelab_ha_discovery.collectors.cpu_top import parse_cpu_usage, run_top
from homelab_ha_discovery.discovery import (
    MetricIdentity,
    mqtt_topic_prefix,
    sensor_discovery_config,
)
from homelab_ha_discovery.env import load_env_files
from homelab_ha_discovery.mqtt import publish_mqtt
from homelab_ha_discovery.scripts.timer import (
    run_publish_timer,
    validate_timer_seconds,
)


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)


def cpu_usage_identity(
    device: str,
    state_topic_override: str | None = None,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component="cpu",
        metric="usage",
        state_topic_override=state_topic_override
        or f"{mqtt_topic_prefix()}/cpu/usages/{device}",
    )


def cpu_usage_client_id(device: str) -> str:
    if not device:
        raise ValueError("device is required")
    return f"homelab-ha-discovery_{device}_cpu_usage"


def publish_cpu_discovery(identity: MetricIdentity, device: str) -> None:
    config = sensor_discovery_config(
        identity,
        name=f"{device} CPU Usage",
        unit_of_measurement="%",
        state_class="measurement",
        value_template="{{ value_json['CPU Usages'] }}",
    )
    payload = json.dumps(config, separators=(",", ":"))
    publish_mqtt(
        identity.discovery_topic,
        payload,
        default_client_id=cpu_usage_client_id(device),
        retain=True,
    )


def publish_cpu_usage(
    env_files: tuple[str, ...],
    device: str,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
) -> int:
    try:
        load_env_files(env_files)
        identity = cpu_usage_identity(device)
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic or identity.state_topic,
        )
        identity = cpu_usage_identity(device, state_topic_override=mqtt_topic)
        if not publisher_only:
            publish_cpu_discovery(identity, device)

        cpu_usage = parse_cpu_usage(run_top())
        payload = json.dumps({"CPU Usages": cpu_usage}, separators=(",", ":"))
        publish_mqtt(mqtt_topic, payload, default_client_id=cpu_usage_client_id(device))
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
        parser.error("the following arguments are required: --device")
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

    next_discovery_publish_at = 0.0 if not args.publisher_only else None

    def publish() -> int:
        nonlocal next_discovery_publish_at
        publish_discovery = (
            next_discovery_publish_at is not None
            and time.monotonic() >= next_discovery_publish_at
        )
        result = publish_cpu_usage(
            DEFAULT_ENV_FILES,
            args.device,
            publisher_only=not publish_discovery,
        )
        if result == 0 and publish_discovery:
            if args.timer_publish_discovery_config is None:
                next_discovery_publish_at = None
            else:
                next_discovery_publish_at = (
                    time.monotonic() + args.timer_publish_discovery_config
                )
        return result

    return run_publish_timer(args.timer, publish)


if __name__ == "__main__":
    raise SystemExit(main())
