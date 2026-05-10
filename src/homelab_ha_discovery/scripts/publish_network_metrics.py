"""Publish Linux network throughput metrics."""

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

from homelab_ha_discovery.collectors.network_linux import (
    NetworkCounterSample,
    calculate_network_speed_metrics,
    read_network_counter_sample,
)
from homelab_ha_discovery.discovery import (
    MetricIdentity,
    mqtt_topic_prefix,
    sensor_discovery_config,
)
from homelab_ha_discovery.env import load_env_files
from homelab_ha_discovery.mqtt import publish_mqtt
from homelab_ha_discovery.scripts.timer import validate_timer_seconds


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)
DEFAULT_SAMPLE_INTERVAL_SECONDS = 1.0


def network_component_from_dev(dev: str) -> str:
    component = dev.strip()
    if not component:
        raise ValueError("network interface is required")
    return component


def network_metrics_state_topic(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"{mqtt_topic_prefix()}/{component}/metrics/{device}"


def network_metric_identity(
    device: str,
    component: str,
    metric: str,
    state_topic: str,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component=component,
        metric=metric,
        state_topic_override=state_topic,
    )


def network_metrics_client_id(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"homelab-ha-discovery_{device}_{component}_metrics"


def publish_network_discovery(device: str, component: str, state_topic: str) -> None:
    configs = (
        (
            network_metric_identity(device, component, "download_speed", state_topic),
            f"{device} {component} Download Speed",
            "KB/s",
            "{{ value_json['Download Speed'] }}",
        ),
        (
            network_metric_identity(device, component, "upload_speed", state_topic),
            f"{device} {component} Upload Speed",
            "KB/s",
            "{{ value_json['Upload Speed'] }}",
        ),
    )
    for identity, name, unit_of_measurement, value_template in configs:
        payload = json.dumps(
            sensor_discovery_config(
                identity,
                name=name,
                unit_of_measurement=unit_of_measurement,
                state_class="measurement",
                value_template=value_template,
            ),
            separators=(",", ":"),
        )
        publish_mqtt(
            identity.discovery_topic,
            payload,
            default_client_id=network_metrics_client_id(device, component),
            retain=True,
        )


def publish_network_metrics_from_samples(
    env_files: tuple[str, ...],
    device: str,
    dev: str,
    previous_sample: NetworkCounterSample,
    current_sample: NetworkCounterSample,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
) -> int:
    try:
        metrics = calculate_network_speed_metrics(previous_sample, current_sample)
        load_env_files(env_files)
        component = network_component_from_dev(dev)
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic or network_metrics_state_topic(device, component),
        )
        if not publisher_only:
            publish_network_discovery(device, component, mqtt_topic)

        payload = json.dumps(metrics, separators=(",", ":"))
        publish_mqtt(
            mqtt_topic,
            payload,
            default_client_id=network_metrics_client_id(device, component),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def publish_network_metrics(
    env_files: tuple[str, ...],
    device: str,
    dev: str,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
) -> int:
    try:
        previous_sample = read_network_counter_sample(dev)
        time.sleep(DEFAULT_SAMPLE_INTERVAL_SECONDS)
        current_sample = read_network_counter_sample(dev)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return publish_network_metrics_from_samples(
        env_files,
        device,
        dev,
        previous_sample,
        current_sample,
        default_mqtt_topic=default_mqtt_topic,
        publisher_only=publisher_only,
    )


def run_network_publish_timer(
    timer: float,
    device: str,
    dev: str,
    publisher_only: bool = False,
    timer_publish_discovery_config: float | None = None,
) -> int:
    next_discovery_publish_at = 0.0 if not publisher_only else None
    try:
        previous_sample = read_network_counter_sample(dev)
        while True:
            time.sleep(timer)
            current_sample = read_network_counter_sample(dev)
            publish_discovery = (
                next_discovery_publish_at is not None
                and time.monotonic() >= next_discovery_publish_at
            )
            result = publish_network_metrics_from_samples(
                DEFAULT_ENV_FILES,
                device,
                dev,
                previous_sample,
                current_sample,
                publisher_only=not publish_discovery,
            )
            if result != 0:
                return result
            previous_sample = current_sample
            if publish_discovery:
                if timer_publish_discovery_config is None:
                    next_discovery_publish_at = None
                else:
                    next_discovery_publish_at = (
                        time.monotonic() + timer_publish_discovery_config
                    )
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device")
    parser.add_argument("--host", dest="device", help=argparse.SUPPRESS)
    parser.add_argument(
        "--dev",
        help="Network interface name from psutil, for example ppp0.",
    )
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
    if not args.dev:
        parser.error("the following arguments are required: --dev")
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

    if args.timer is not None:
        return run_network_publish_timer(
            args.timer,
            args.device,
            args.dev,
            publisher_only=args.publisher_only,
            timer_publish_discovery_config=args.timer_publish_discovery_config,
        )

    return publish_network_metrics(
        DEFAULT_ENV_FILES,
        args.device,
        args.dev,
        publisher_only=args.publisher_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
