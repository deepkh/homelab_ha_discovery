"""Publish NVMe SMART metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.nvme_smart import (
    parse_nvme_smart_metrics,
    run_smartctl,
)
from homelab_ha_discovery.discovery import (
    MetricIdentity,
    effective_expire_after,
    mqtt_topic_prefix,
    sensor_discovery_config,
    validate_expire_after_seconds,
)
from homelab_ha_discovery.env import load_env_files
from homelab_ha_discovery.mqtt import MqttMessage, publish_mqtt_many
from homelab_ha_discovery.scripts.timer import (
    run_publish_timer,
    validate_timer_seconds,
)


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)
NVME_COMPONENT_RE = re.compile(r"[^a-z0-9_]+")


def nvme_component_from_dev(dev: str) -> str:
    component = NVME_COMPONENT_RE.sub("_", Path(dev.strip()).name.lower()).strip("_")
    if not component:
        raise ValueError("could not derive NVMe component from --dev")
    return component


def nvme_metrics_state_topic(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"{mqtt_topic_prefix()}/{component}/metrics/{device}"


def nvme_metric_identity(
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


def nvme_metrics_client_id(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"homelab-ha-discovery_{device}_{component}_metrics"


def nvme_discovery_messages(
    device: str,
    component: str,
    state_topic: str,
    expire_after: float | None = None,
) -> list[MqttMessage]:
    messages: list[MqttMessage] = []
    configs = (
        (
            nvme_metric_identity(device, component, "critical_warning", state_topic),
            f"{device} {component} Critical Warning",
            None,
            None,
            "{{ value_json['Critical Warning'] }}",
        ),
        (
            nvme_metric_identity(
                device,
                component,
                "media_data_integrity_errors",
                state_topic,
            ),
            f"{device} {component} Media and Data Integrity Errors",
            None,
            None,
            "{{ value_json['Media and Data Integrity Errors'] }}",
        ),
        (
            nvme_metric_identity(device, component, "available_spare", state_topic),
            f"{device} {component} Available Spare",
            "%",
            None,
            "{{ value_json['Available Spare'] }}",
        ),
        (
            nvme_metric_identity(device, component, "percentage_used", state_topic),
            f"{device} {component} Percentage Used",
            "%",
            None,
            "{{ value_json['Percentage Used'] }}",
        ),
        (
            nvme_metric_identity(
                device,
                component,
                "critical_temperature_time",
                state_topic,
            ),
            f"{device} {component} Critical Temperature Time",
            "min",
            None,
            "{{ value_json['Critical Temperature Time'] }}",
        ),
        (
            nvme_metric_identity(device, component, "temperature_c", state_topic),
            f"{device} {component} Temperature",
            "°C",
            "temperature",
            "{{ value_json['temperature_c'] }}",
        ),
        (
            nvme_metric_identity(device, component, "data_written_tb", state_topic),
            f"{device} {component} Data Written",
            "TB",
            None,
            "{{ value_json['data_written_tb'] }}",
        ),
        (
            nvme_metric_identity(device, component, "power_on_hours", state_topic),
            f"{device} {component} Power On Hours",
            "h",
            None,
            "{{ value_json['power_on_hours'] }}",
        ),
    )
    for identity, name, unit_of_measurement, device_class, value_template in configs:
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


def publish_nvme_discovery(
    device: str,
    component: str,
    state_topic: str,
    expire_after: float | None = None,
) -> None:
    publish_mqtt_many(
        nvme_discovery_messages(
            device,
            component,
            state_topic,
            expire_after=expire_after,
        ),
        default_client_id=nvme_metrics_client_id(device, component),
    )


def publish_nvme_metrics(
    env_files: tuple[str, ...],
    device: str,
    dev: str,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
    expire_after: float | None = None,
) -> int:
    try:
        load_env_files(env_files)
        component = nvme_component_from_dev(dev)
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic or nvme_metrics_state_topic(device, component),
        )
        metrics = parse_nvme_smart_metrics(run_smartctl(dev))
        mqtt_messages: list[MqttMessage] = []
        if not publisher_only:
            mqtt_messages.extend(
                nvme_discovery_messages(
                    device,
                    component,
                    mqtt_topic,
                    expire_after=expire_after,
                )
            )

        payload = json.dumps(metrics, separators=(",", ":"))
        mqtt_messages.append((mqtt_topic, payload, False))
        publish_mqtt_many(
            mqtt_messages,
            default_client_id=nvme_metrics_client_id(device, component),
        )
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
        "--dev",
        help="NVMe controller device path to pass to smartctl, for example /dev/nvme0.",
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
    if not validate_expire_after_seconds(args.expire_after):
        return 1

    expire_after = effective_expire_after(args.expire_after, args.timer)

    next_discovery_publish_at = 0.0 if not args.publisher_only else None

    def publish() -> int:
        nonlocal next_discovery_publish_at
        publish_discovery = (
            next_discovery_publish_at is not None
            and time.monotonic() >= next_discovery_publish_at
        )
        result = publish_nvme_metrics(
            DEFAULT_ENV_FILES,
            args.device,
            args.dev,
            publisher_only=not publish_discovery,
            expire_after=expire_after,
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
