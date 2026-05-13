"""Publish Podman container metrics."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import time

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.podman_containers import (
    LabelSelectors,
    PodmanContainerSample,
    calculate_podman_container_metrics,
    parse_label_selector,
    read_podman_container_sample,
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
from homelab_ha_discovery.scripts.timer import validate_timer_seconds


DEFAULT_ENV_FILES = (
    "/etc/homelab-ha-discovery/mqtt.env",
)
DEFAULT_SAMPLE_INTERVAL_SECONDS = 1.0
PODMAN_SCOPE_RE = re.compile(r"[^a-z0-9_]+")


def debug_log(debug: bool, message: str) -> None:
    if debug:
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        print(f"DEBUG: {timestamp} {message}", file=sys.stderr, flush=True)


def debug_sample(
    debug: bool,
    label: str,
    sample: PodmanContainerSample,
) -> None:
    if not debug:
        return
    debug_log(
        debug,
        (
            f"{label}: included_containers={len(sample.containers)} "
            f"stats_rows={len(sample.stats)}"
        ),
    )
    for container in sorted(
        sample.containers.values(),
        key=lambda item: item.component,
    ):
        stats_status = "yes" if container.container_id in sample.stats else "no"
        debug_log(
            debug,
            (
                f"{label}: component={container.component} name={container.name} "
                f"state={container.state} health={container.health} "
                f"restart_count={container.restart_count} stats={stats_status}"
            ),
        )


def podman_scope_from_value(value: str) -> str:
    scope = PODMAN_SCOPE_RE.sub("_", value.strip().lower()).strip("_")
    if not scope:
        raise ValueError("Podman scope is required")
    return scope


def podman_metrics_state_topic(device: str, scope: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not scope:
        raise ValueError("Podman scope is required")
    if not component:
        raise ValueError("Podman component is required")
    return f"{mqtt_topic_prefix()}/{device}/podman/{scope}/{component}/metrics"


def podman_metric_identity(
    device: str,
    scope: str,
    component: str,
    metric: str,
    state_topic: str,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component=f"podman_{scope}_{component}",
        metric=metric,
        state_topic_override=state_topic,
    )


def podman_metrics_client_id(
    device: str,
    scope: str,
    component: str | None = None,
) -> str:
    if not device:
        raise ValueError("device is required")
    if not scope:
        raise ValueError("Podman scope is required")
    if component:
        return f"homelab-ha-discovery_{device}_podman_{scope}_{component}_metrics"
    return f"homelab-ha-discovery_{device}_podman_{scope}_metrics"


def podman_discovery_configs(
    device: str,
    scope: str,
    component: str,
    container_name: str,
    state_topic: str,
) -> tuple[tuple[MetricIdentity, str, str | None, str | None], ...]:
    prefix = f"{device} Podman {scope} {container_name}"
    return (
        (
            podman_metric_identity(device, scope, component, "state", state_topic),
            f"{prefix} State",
            None,
            "{{ value_json['State'] }}",
        ),
        (
            podman_metric_identity(device, scope, component, "health", state_topic),
            f"{prefix} Health",
            None,
            "{{ value_json['Health'] }}",
        ),
        (
            podman_metric_identity(
                device,
                scope,
                component,
                "restart_count",
                state_topic,
            ),
            f"{prefix} Restart Count",
            None,
            "{{ value_json['Restart Count'] }}",
        ),
        (
            podman_metric_identity(
                device,
                scope,
                component,
                "cpu_usage",
                state_topic,
            ),
            f"{prefix} CPU Usage",
            "%",
            "{{ value_json['CPU Usage'] }}",
        ),
        (
            podman_metric_identity(
                device,
                scope,
                component,
                "memory_usage_mb",
                state_topic,
            ),
            f"{prefix} Memory Usage",
            "MB",
            "{{ value_json['Memory Usage MB'] }}",
        ),
        (
            podman_metric_identity(
                device,
                scope,
                component,
                "memory_limit_mb",
                state_topic,
            ),
            f"{prefix} Memory Limit",
            "MB",
            "{{ value_json['Memory Limit MB'] }}",
        ),
        (
            podman_metric_identity(
                device,
                scope,
                component,
                "memory_usage_percent",
                state_topic,
            ),
            f"{prefix} Memory Usage Percent",
            "%",
            "{{ value_json['Memory Usage Percent'] }}",
        ),
        (
            podman_metric_identity(
                device,
                scope,
                component,
                "download_speed",
                state_topic,
            ),
            f"{prefix} Download Speed",
            "Mbps",
            "{{ value_json['Download Speed'] }}",
        ),
        (
            podman_metric_identity(
                device,
                scope,
                component,
                "upload_speed",
                state_topic,
            ),
            f"{prefix} Upload Speed",
            "Mbps",
            "{{ value_json['Upload Speed'] }}",
        ),
    )


def podman_container_discovery_messages(
    device: str,
    scope: str,
    component: str,
    container_name: str,
    state_topic: str,
    expire_after: float | None = None,
    debug: bool = False,
) -> list[MqttMessage]:
    messages: list[MqttMessage] = []
    for (
        identity,
        name,
        unit_of_measurement,
        value_template,
    ) in podman_discovery_configs(
        device,
        scope,
        component,
        container_name,
        state_topic,
    ):
        state_class = "measurement" if unit_of_measurement is not None else None
        config = sensor_discovery_config(
            identity,
            name=name,
            unit_of_measurement=unit_of_measurement,
            state_class=state_class,
            value_template=value_template,
            expire_after=expire_after,
        )
        payload = json.dumps(
            config,
            separators=(",", ":"),
        )
        debug_log(debug, f"queueing discovery config to {identity.discovery_topic}")
        messages.append((identity.discovery_topic, payload, True))
    return messages


def publish_podman_container_discovery(
    device: str,
    scope: str,
    component: str,
    container_name: str,
    state_topic: str,
    expire_after: float | None = None,
    debug: bool = False,
) -> None:
    scope = podman_scope_from_value(scope)
    messages = podman_container_discovery_messages(
        device,
        scope,
        component,
        container_name,
        state_topic,
        expire_after=expire_after,
        debug=debug,
    )
    debug_log(
        debug,
        f"publishing {len(messages)} MQTT discovery message(s) in one connection",
    )
    publish_mqtt_many(
        messages,
        default_client_id=podman_metrics_client_id(device, scope, component),
    )


def publish_podman_metrics_from_samples(
    env_files: tuple[str, ...],
    device: str,
    scope: str,
    previous_sample: PodmanContainerSample,
    current_sample: PodmanContainerSample,
    publisher_only: bool = False,
    discovery_components: set[str] | None = None,
    expire_after: float | None = None,
    debug: bool = False,
    mqtt_publisher: MqttPublisher | None = None,
) -> int:
    try:
        scope = podman_scope_from_value(scope)
        debug_sample(debug, "previous sample", previous_sample)
        debug_sample(debug, "current sample", current_sample)
        metrics, skipped_components = calculate_podman_container_metrics(
            previous_sample,
            current_sample,
        )
        debug_log(
            debug,
            (
                f"calculated Podman metrics: metrics={len(metrics)} "
                f"skipped={len(skipped_components)} "
                f"publisher_only={publisher_only}"
            ),
        )
        if not current_sample.containers:
            debug_log(
                debug,
                (
                    "no Podman containers matched; check --include-label filters "
                    "or run without --include-label"
                ),
            )
        if mqtt_publisher is None:
            debug_log(debug, "loading MQTT environment files")
            load_env_files(env_files)
        else:
            debug_log(debug, "using existing MQTT publisher")

        mqtt_messages: list[MqttMessage] = []
        if not publisher_only:
            for container in sorted(
                current_sample.containers.values(),
                key=lambda item: item.component,
            ):
                if (
                    discovery_components is not None
                    and container.component not in discovery_components
                ):
                    continue
                state_topic = podman_metrics_state_topic(
                    device,
                    scope,
                    container.component,
                )
                mqtt_messages.extend(
                    podman_container_discovery_messages(
                        device,
                        scope,
                        container.component,
                        container.name,
                        state_topic,
                        expire_after=expire_after,
                        debug=debug,
                    )
                )

        for component in skipped_components:
            print(
                "Skipping Podman container without previous network sample: "
                f"{component}",
                file=sys.stderr,
            )

        for item in metrics:
            mqtt_topic = podman_metrics_state_topic(device, scope, item.component)
            payload = json.dumps(item.payload, separators=(",", ":"))
            debug_log(
                debug,
                f"queueing Podman state payload to {mqtt_topic}: {payload}",
            )
            mqtt_messages.append((mqtt_topic, payload, False))

        debug_log(
            debug,
            f"publishing {len(mqtt_messages)} MQTT message(s) in one connection",
        )
        if mqtt_publisher is None:
            publish_mqtt_many(
                mqtt_messages,
                default_client_id=podman_metrics_client_id(device, scope),
            )
        else:
            mqtt_publisher.publish_many(mqtt_messages)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def publish_podman_metrics(
    env_files: tuple[str, ...],
    device: str,
    scope: str,
    podman_command: str = "podman",
    include_all: bool = False,
    include_label_selectors: LabelSelectors = (),
    publisher_only: bool = False,
    expire_after: float | None = None,
    debug: bool = False,
    mqtt_publisher: MqttPublisher | None = None,
) -> int:
    try:
        scope = podman_scope_from_value(scope)
        debug_log(
            debug,
            (
                "reading Podman baseline sample: "
                f"podman_command={podman_command} podman_scope={scope} "
                f"include_all={include_all} "
                f"include_labels={include_label_selectors}"
            ),
        )
        previous_sample = read_podman_container_sample(
            podman_command=podman_command,
            include_all=include_all,
            include_label_selectors=include_label_selectors,
        )
        debug_sample(debug, "baseline sample", previous_sample)
        debug_log(
            debug,
            f"sleeping {DEFAULT_SAMPLE_INTERVAL_SECONDS} seconds before current sample",
        )
        time.sleep(DEFAULT_SAMPLE_INTERVAL_SECONDS)
        debug_log(debug, "reading Podman current sample")
        current_sample = read_podman_container_sample(
            podman_command=podman_command,
            include_all=include_all,
            include_label_selectors=include_label_selectors,
        )
        debug_sample(debug, "current sample", current_sample)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return publish_podman_metrics_from_samples(
        env_files,
        device,
        scope,
        previous_sample,
        current_sample,
        publisher_only=publisher_only,
        expire_after=expire_after,
        debug=debug,
        mqtt_publisher=mqtt_publisher,
    )


def run_podman_publish_timer(
    timer: float,
    device: str,
    scope: str,
    podman_command: str = "podman",
    include_all: bool = False,
    include_label_selectors: LabelSelectors = (),
    publisher_only: bool = False,
    timer_publish_discovery_config: float | None = None,
    expire_after: float | None = None,
    debug: bool = False,
) -> int:
    next_discovery_publish_at = 0.0 if not publisher_only else None
    discovered_components: set[str] = set()
    try:
        scope = podman_scope_from_value(scope)
        load_env_files(DEFAULT_ENV_FILES)
        debug_log(
            debug,
            (
                "starting Podman publish timer: "
                f"timer={timer} device={device} podman_scope={scope} "
                f"podman_command={podman_command} "
                f"include_all={include_all} include_labels={include_label_selectors} "
                f"publisher_only={publisher_only} "
                f"timer_publish_discovery_config={timer_publish_discovery_config} "
                f"expire_after={expire_after}"
            ),
        )
        with MqttPublisher(
            default_client_id=podman_metrics_client_id(device, scope),
        ) as mqtt_publisher:
            debug_log(debug, "reading Podman baseline sample")
            previous_sample = read_podman_container_sample(
                podman_command=podman_command,
                include_all=include_all,
                include_label_selectors=include_label_selectors,
            )
            debug_sample(debug, "baseline sample", previous_sample)
            while True:
                debug_log(debug, f"sleeping {timer} seconds before next Podman sample")
                time.sleep(timer)
                debug_log(debug, "reading Podman current sample")
                current_sample = read_podman_container_sample(
                    podman_command=podman_command,
                    include_all=include_all,
                    include_label_selectors=include_label_selectors,
                )
                publish_discovery = (
                    next_discovery_publish_at is not None
                    and time.monotonic() >= next_discovery_publish_at
                )
                current_components = {
                    container.component
                    for container in current_sample.containers.values()
                }
                new_components = current_components - discovered_components
                discovery_components = None if publish_discovery else new_components
                should_publish_discovery = (
                    not publisher_only
                    and (publish_discovery or bool(discovery_components))
                )
                debug_log(
                    debug,
                    (
                        f"timer publish decision: publish_discovery="
                        f"{publish_discovery} "
                        f"new_components={sorted(new_components)} "
                        f"should_publish_discovery={should_publish_discovery}"
                    ),
                )
                result = publish_podman_metrics_from_samples(
                    DEFAULT_ENV_FILES,
                    device,
                    scope,
                    previous_sample,
                    current_sample,
                    publisher_only=not should_publish_discovery,
                    discovery_components=discovery_components,
                    expire_after=expire_after,
                    debug=debug,
                    mqtt_publisher=mqtt_publisher,
                )
                if result != 0:
                    return result
                previous_sample = current_sample
                if should_publish_discovery:
                    if discovery_components is None:
                        discovered_components.update(current_components)
                    else:
                        discovered_components.update(discovery_components)
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


def parse_label_selectors(values: list[str] | None) -> LabelSelectors:
    return tuple(parse_label_selector(value) for value in values or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ha-device-id",
        dest="device",
        help="Stable Home Assistant/MQTT device identity.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include stopped containers as well as running containers.",
    )
    parser.add_argument(
        "--include-label",
        action="append",
        default=[],
        metavar="KEY[=VALUE]",
        help=(
            "Only publish containers with this Podman label. Repeat to require "
            "multiple labels."
        ),
    )
    parser.add_argument(
        "--podman-command",
        default="podman",
        help="Podman CLI command path. Default: podman",
    )
    parser.add_argument(
        "--podman-scope",
        default="root",
        help=(
            "Stable Podman scope for MQTT topics and discovery IDs. Use root "
            "for root containers and a username for rootless containers. "
            "Default: root"
        ),
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

    try:
        scope = podman_scope_from_value(args.podman_scope)
        include_label_selectors = parse_label_selectors(args.include_label)
    except ValueError as exc:
        parser.error(str(exc))

    expire_after = effective_expire_after(args.expire_after, args.timer)

    if args.timer is not None:
        return run_podman_publish_timer(
            args.timer,
            args.device,
            scope,
            podman_command=args.podman_command,
            include_all=args.all,
            include_label_selectors=include_label_selectors,
            publisher_only=args.publisher_only,
            timer_publish_discovery_config=args.timer_publish_discovery_config,
            expire_after=expire_after,
            debug=args.debug,
        )

    return publish_podman_metrics(
        DEFAULT_ENV_FILES,
        args.device,
        scope,
        podman_command=args.podman_command,
        include_all=args.all,
        include_label_selectors=include_label_selectors,
        publisher_only=args.publisher_only,
        expire_after=expire_after,
        debug=args.debug,
    )


if __name__ == "__main__":
    raise SystemExit(main())
