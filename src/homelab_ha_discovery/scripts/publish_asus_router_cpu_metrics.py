"""Publish ASUS router CPU metrics collected over SSH."""

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

from homelab_ha_discovery.collectors.router_asus_ssh import (
    DEFAULT_SSH_PORT,
    DEFAULT_TEMPERATURE_COMMAND,
    DEFAULT_TOP_COMMAND,
    parse_asus_router_cpu_temperature,
    parse_asus_router_cpu_usage,
    run_asus_router_thermal_temps,
    run_asus_router_top,
    validate_ssh_port,
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
ROUTER_COMPONENT_RE = re.compile(r"[^a-z0-9_]+")


def debug_log(debug: bool, message: str) -> None:
    if debug:
        print(f"DEBUG: {message}", file=sys.stderr, flush=True)


def router_component_from_name(router_name: str) -> str:
    component = ROUTER_COMPONENT_RE.sub(
        "_",
        router_name.strip().lower(),
    ).strip("_")
    if not component:
        raise ValueError("router name is required")
    return component


def asus_router_cpu_metrics_state_topic(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"{mqtt_topic_prefix()}/{component}/cpu/metrics/{device}"


def asus_router_cpu_metric_identity(
    device: str,
    component: str,
    metric: str,
    state_topic: str,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component=f"{component}_cpu",
        metric=metric,
        state_topic_override=state_topic,
    )


def asus_router_cpu_metrics_client_id(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"homelab-ha-discovery_{device}_{component}_cpu_metrics"


def publish_asus_router_cpu_discovery(
    device: str,
    router_name: str,
    component: str,
    state_topic: str,
    debug: bool = False,
    expire_after: float | None = None,
) -> None:
    messages = asus_router_cpu_discovery_messages(
        device,
        router_name,
        component,
        state_topic,
        expire_after=expire_after,
        debug=debug,
    )
    publish_mqtt_many(
        messages,
        default_client_id=asus_router_cpu_metrics_client_id(device, component),
    )


def asus_router_cpu_discovery_messages(
    device: str,
    router_name: str,
    component: str,
    state_topic: str,
    expire_after: float | None = None,
    debug: bool = False,
) -> list[MqttMessage]:
    messages: list[MqttMessage] = []
    configs = (
        (
            asus_router_cpu_metric_identity(device, component, "usage", state_topic),
            f"{device} {router_name} CPU Usage",
            "%",
            None,
            "{{ value_json['CPU Usages'] }}",
        ),
        (
            asus_router_cpu_metric_identity(
                device,
                component,
                "temperature",
                state_topic,
            ),
            f"{device} {router_name} CPU Temperature",
            "\u00b0C",
            "temperature",
            "{{ value_json['Temperature'] }}",
        ),
    )
    for identity, name, unit_of_measurement, device_class, value_template in configs:
        debug_log(debug, f"queueing discovery config to {identity.discovery_topic}")
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


def publish_asus_router_cpu_metrics(
    env_files: tuple[str, ...],
    device: str,
    router_name: str,
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    top_command: str = DEFAULT_TOP_COMMAND,
    temperature_command: str = DEFAULT_TEMPERATURE_COMMAND,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
    debug: bool = False,
    expire_after: float | None = None,
) -> int:
    try:
        debug_log(debug, "loading MQTT environment files")
        load_env_files(env_files)
        component = router_component_from_name(router_name)
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic
            or asus_router_cpu_metrics_state_topic(device, component),
        )
        debug_log(debug, f"router component is {component}")
        debug_log(debug, f"state topic is {mqtt_topic}")
        debug_log(
            debug,
            f"running SSH top command on {ssh_user}@{ssh_ip}:{ssh_port}: "
            f"{top_command}",
        )
        top_output = run_asus_router_top(
            ssh_user,
            ssh_ip,
            ssh_port=ssh_port,
            top_command=top_command,
        )
        debug_log(debug, f"received {len(top_output)} bytes from top command")
        cpu_usage = parse_asus_router_cpu_usage(top_output)
        debug_log(debug, f"parsed CPU usage: {cpu_usage}")
        debug_log(
            debug,
            f"running SSH thermal command on {ssh_user}@{ssh_ip}:{ssh_port}: "
            f"{temperature_command}",
        )
        thermal_output = run_asus_router_thermal_temps(
            ssh_user,
            ssh_ip,
            ssh_port=ssh_port,
            temperature_command=temperature_command,
        )
        debug_log(debug, f"received {len(thermal_output)} bytes from thermal command")
        temperature = parse_asus_router_cpu_temperature(thermal_output)
        debug_log(debug, f"parsed temperature: {temperature}")
        metrics = {
            "CPU Usages": cpu_usage,
            "Temperature": temperature,
        }
        mqtt_messages: list[MqttMessage] = []
        if not publisher_only:
            mqtt_messages.extend(
                asus_router_cpu_discovery_messages(
                    device,
                    router_name,
                    component,
                    mqtt_topic,
                    expire_after=expire_after,
                    debug=debug,
                )
            )

        payload = json.dumps(metrics, separators=(",", ":"))
        debug_log(debug, f"queueing state payload to {mqtt_topic}: {payload}")
        mqtt_messages.append((mqtt_topic, payload, False))
        debug_log(
            debug,
            f"publishing {len(mqtt_messages)} MQTT message(s) in one connection",
        )
        publish_mqtt_many(
            mqtt_messages,
            default_client_id=asus_router_cpu_metrics_client_id(device, component),
        )
        debug_log(debug, "publish completed")
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
        "--router-name",
        help="Stable router name used for MQTT and Home Assistant component IDs.",
    )
    parser.add_argument(
        "--ssh-user",
        help="SSH username for the ASUS router.",
    )
    parser.add_argument(
        "--ssh-ip",
        help="SSH IP address or hostname for the ASUS router.",
    )
    parser.add_argument(
        "--ssh-port",
        type=int,
        default=DEFAULT_SSH_PORT,
        help=f"SSH port for the ASUS router. Default: {DEFAULT_SSH_PORT}",
    )
    parser.add_argument(
        "--top-command",
        default=DEFAULT_TOP_COMMAND,
        help=f"Remote CPU usage command. Default: {DEFAULT_TOP_COMMAND!r}",
    )
    parser.add_argument(
        "--temperature-command",
        default=DEFAULT_TEMPERATURE_COMMAND,
        help=(
            "Remote thermal-zone command. "
            f"Default: {DEFAULT_TEMPERATURE_COMMAND!r}"
        ),
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
        "--debug",
        action="store_true",
        help="Print progress messages to stderr while collecting and publishing.",
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
    if not args.router_name:
        parser.error("the following arguments are required: --router-name")
    if not args.ssh_user:
        parser.error("the following arguments are required: --ssh-user")
    if not args.ssh_ip:
        parser.error("the following arguments are required: --ssh-ip")
    try:
        validate_ssh_port(args.ssh_port)
    except ValueError as exc:
        parser.error(str(exc))
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
        result = publish_asus_router_cpu_metrics(
            DEFAULT_ENV_FILES,
            args.device,
            args.router_name,
            args.ssh_user,
            args.ssh_ip,
            ssh_port=args.ssh_port,
            top_command=args.top_command,
            temperature_command=args.temperature_command,
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
