"""Publish Frigate metrics from the local Prometheus endpoint."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import time

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.frigate_metrics import (  # noqa: E402
    DEFAULT_FRIGATE_HTTP_TIMEOUT_SECONDS,
    DEFAULT_FRIGATE_METRICS_URL,
    FrigateMetrics,
    read_frigate_metrics,
)
from homelab_ha_discovery.discovery import (  # noqa: E402
    MetricIdentity,
    effective_expire_after,
    mqtt_topic_prefix,
    sensor_discovery_config,
    validate_expire_after_seconds,
)
from homelab_ha_discovery.env import load_env_files  # noqa: E402
from homelab_ha_discovery.mqtt import MqttMessage, publish_mqtt_many  # noqa: E402
from homelab_ha_discovery.scripts.timer import (  # noqa: E402
    run_publish_timer,
    validate_timer_seconds,
)


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)
FRIGATE_COMPONENT_RE = re.compile(r"[^a-z0-9_]+")


def debug_log(debug: bool, message: str) -> None:
    if debug:
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        print(f"DEBUG: {timestamp} {message}", file=sys.stderr, flush=True)


def frigate_component_from_label(label: str) -> str:
    text = label.strip()
    if text == "/":
        return "root"
    component = FRIGATE_COMPONENT_RE.sub("_", text.lower()).strip("_")
    if not component:
        raise ValueError(f"could not derive Frigate component from {label!r}")
    return component


def normalized_label_components(labels: object, section: str) -> dict[str, str]:
    if not isinstance(labels, dict):
        raise ValueError(f"Frigate {section} metrics must be a JSON object")
    components: dict[str, str] = {}
    labels_by_component: dict[str, str] = {}
    for label in labels:
        if not isinstance(label, str):
            raise ValueError(f"Frigate {section} metric label must be a string")
        component = frigate_component_from_label(label)
        previous = labels_by_component.get(component)
        if previous is not None and previous != label:
            raise ValueError(
                f"multiple Frigate {section} labels normalize to {component!r}: "
                f"{previous!r}, {label!r}"
            )
        labels_by_component[component] = label
        components[label] = component
    return components


def jinja_key(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def jinja_value_template(*keys: str) -> str:
    path = "".join(f"[{jinja_key(key)}]" for key in keys)
    return f"{{{{ value_json{path} }}}}"


def frigate_metrics_state_topic(device: str) -> str:
    if not device:
        raise ValueError("device is required")
    return f"{mqtt_topic_prefix()}/frigate/metrics/{device}"


def frigate_metric_identity(
    device: str,
    component: str,
    metric: str,
    state_topic: str,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component=f"frigate_{component}",
        metric=metric,
        state_topic_override=state_topic,
    )


def frigate_metrics_client_id(device: str) -> str:
    if not device:
        raise ValueError("device is required")
    return f"homelab-ha-discovery_{device}_frigate_metrics"


def frigate_discovery_messages(
    device: str,
    state_topic: str,
    metrics: FrigateMetrics,
    expire_after: float | None = None,
    debug: bool = False,
) -> list[MqttMessage]:
    messages: list[MqttMessage] = []

    configs: list[tuple[MetricIdentity, str, str, str]] = [
        (
            frigate_metric_identity(device, "system", "cpu_usage", state_topic),
            f"{device} Frigate System CPU Usage",
            "%",
            jinja_value_template("system", "CPU Usage"),
        ),
        (
            frigate_metric_identity(device, "system", "memory_usage", state_topic),
            f"{device} Frigate System Memory Usage",
            "%",
            jinja_value_template("system", "Memory Usage"),
        ),
    ]

    camera_components = normalized_label_components(
        metrics.get("cameras"),
        "camera",
    )
    for camera_label in sorted(camera_components, key=camera_components.get):
        component = f"camera_{camera_components[camera_label]}"
        configs.extend(
            (
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "camera_fps",
                        state_topic,
                    ),
                    f"{device} Frigate {camera_label} Camera FPS",
                    "fps",
                    jinja_value_template("cameras", camera_label, "Camera FPS"),
                ),
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "process_fps",
                        state_topic,
                    ),
                    f"{device} Frigate {camera_label} Process FPS",
                    "fps",
                    jinja_value_template("cameras", camera_label, "Process FPS"),
                ),
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "skipped_fps",
                        state_topic,
                    ),
                    f"{device} Frigate {camera_label} Skipped FPS",
                    "fps",
                    jinja_value_template("cameras", camera_label, "Skipped FPS"),
                ),
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "detection_fps",
                        state_topic,
                    ),
                    f"{device} Frigate {camera_label} Detection FPS",
                    "fps",
                    jinja_value_template("cameras", camera_label, "Detection FPS"),
                ),
            )
        )

    detector_components = normalized_label_components(
        metrics.get("detectors"),
        "detector",
    )
    for detector_label in sorted(detector_components, key=detector_components.get):
        component = f"detector_{detector_components[detector_label]}"
        configs.append(
            (
                frigate_metric_identity(
                    device,
                    component,
                    "inference_speed",
                    state_topic,
                ),
                f"{device} Frigate {detector_label} Inference Speed",
                "s",
                jinja_value_template("detectors", detector_label, "Inference Speed"),
            )
        )

    gpu_components = normalized_label_components(
        metrics.get("gpus"),
        "GPU",
    )
    for gpu_label in sorted(gpu_components, key=gpu_components.get):
        component = f"gpu_{gpu_components[gpu_label]}"
        configs.extend(
            (
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "usage",
                        state_topic,
                    ),
                    f"{device} Frigate {gpu_label} GPU Usage",
                    "%",
                    jinja_value_template("gpus", gpu_label, "GPU Usage"),
                ),
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "memory_usage",
                        state_topic,
                    ),
                    f"{device} Frigate {gpu_label} GPU Memory Usage",
                    "%",
                    jinja_value_template("gpus", gpu_label, "Memory Usage"),
                ),
            )
        )

    storage_components = normalized_label_components(
        metrics.get("storage"),
        "storage",
    )
    for storage_label in sorted(storage_components, key=storage_components.get):
        component = f"storage_{storage_components[storage_label]}"
        configs.extend(
            (
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "free_gb",
                        state_topic,
                    ),
                    f"{device} Frigate {storage_label} Free",
                    "GB",
                    jinja_value_template("storage", storage_label, "Free GB"),
                ),
                (
                    frigate_metric_identity(
                        device,
                        component,
                        "used_gb",
                        state_topic,
                    ),
                    f"{device} Frigate {storage_label} Used",
                    "GB",
                    jinja_value_template("storage", storage_label, "Used GB"),
                ),
            )
        )

    for identity, name, unit_of_measurement, value_template in configs:
        payload = json.dumps(
            sensor_discovery_config(
                identity,
                name=name,
                unit_of_measurement=unit_of_measurement,
                state_class="measurement",
                value_template=value_template,
                expire_after=expire_after,
            ),
            separators=(",", ":"),
        )
        debug_log(debug, f"queueing discovery config to {identity.discovery_topic}")
        messages.append((identity.discovery_topic, payload, True))
    return messages


def publish_frigate_discovery(
    device: str,
    state_topic: str,
    metrics: FrigateMetrics,
    expire_after: float | None = None,
    debug: bool = False,
) -> None:
    messages = frigate_discovery_messages(
        device,
        state_topic,
        metrics,
        expire_after=expire_after,
        debug=debug,
    )
    debug_log(
        debug,
        f"publishing {len(messages)} MQTT discovery message(s) in one connection",
    )
    publish_mqtt_many(
        messages,
        default_client_id=frigate_metrics_client_id(device),
    )


def publish_frigate_metrics(
    env_files: tuple[str, ...],
    device: str,
    url: str = DEFAULT_FRIGATE_METRICS_URL,
    publisher_only: bool = False,
    expire_after: float | None = None,
    debug: bool = False,
) -> int:
    try:
        debug_log(debug, f"reading Frigate metrics from {url}")
        metrics = read_frigate_metrics(
            url,
            timeout=DEFAULT_FRIGATE_HTTP_TIMEOUT_SECONDS,
        )
        debug_log(debug, "loading MQTT environment files")
        load_env_files(env_files)

        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            frigate_metrics_state_topic(device),
        )
        mqtt_messages: list[MqttMessage] = []
        if not publisher_only:
            mqtt_messages.extend(
                frigate_discovery_messages(
                    device,
                    mqtt_topic,
                    metrics,
                    expire_after=expire_after,
                    debug=debug,
                )
            )

        payload = json.dumps(metrics, separators=(",", ":"))
        debug_log(debug, f"queueing Frigate state payload to {mqtt_topic}: {payload}")
        mqtt_messages.append((mqtt_topic, payload, False))
        debug_log(
            debug,
            f"publishing {len(mqtt_messages)} MQTT message(s) in one connection",
        )
        publish_mqtt_many(
            mqtt_messages,
            default_client_id=frigate_metrics_client_id(device),
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
        "--url",
        default=DEFAULT_FRIGATE_METRICS_URL,
        help=f"Frigate Prometheus metrics URL. Default: {DEFAULT_FRIGATE_METRICS_URL}",
    )
    parser.add_argument(
        "--publisher-only",
        action="store_true",
        help="Publish metric state without Home Assistant discovery config.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print progress messages to stderr while collecting and publishing.",
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

    def publish() -> int:
        nonlocal next_discovery_publish_at
        publish_discovery = (
            next_discovery_publish_at is not None
            and time.monotonic() >= next_discovery_publish_at
        )
        result = publish_frigate_metrics(
            DEFAULT_ENV_FILES,
            args.device,
            url=args.url,
            publisher_only=not publish_discovery,
            expire_after=expire_after,
            debug=args.debug,
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
