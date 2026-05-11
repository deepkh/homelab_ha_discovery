"""Publish ASUS router network throughput metrics collected over SSH."""

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
    parse_asus_router_network_metrics,
    run_asus_router_network,
    validate_ssh_port,
)
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
ROUTER_COMPONENT_RE = re.compile(r"[^a-z0-9_]+")


def debug_log(debug: bool, message: str) -> None:
    if debug:
        print(f"DEBUG: {message}", file=sys.stderr, flush=True)


def debug_dump(debug: bool, label: str, text: str) -> None:
    if not debug:
        return
    print(f"DEBUG: {label} begin", file=sys.stderr, flush=True)
    sys.stderr.write(text)
    if text and not text.endswith("\n"):
        sys.stderr.write("\n")
    print(f"DEBUG: {label} end", file=sys.stderr, flush=True)


def router_component_from_name(router_name: str) -> str:
    component = ROUTER_COMPONENT_RE.sub(
        "_",
        router_name.strip().lower(),
    ).strip("_")
    if not component:
        raise ValueError("router name is required")
    return component


def router_interface_component(dev: str) -> str:
    component = dev.strip()
    if not component:
        raise ValueError("network interface is required")
    return component


def asus_router_network_metrics_state_topic(
    device: str,
    router_component: str,
    interface_component: str,
) -> str:
    if not device:
        raise ValueError("device is required")
    if not router_component:
        raise ValueError("router component is required")
    if not interface_component:
        raise ValueError("interface component is required")
    return (
        f"{mqtt_topic_prefix()}/{router_component}/"
        f"{interface_component}/metrics/{device}"
    )


def asus_router_network_metric_identity(
    device: str,
    router_component: str,
    interface_component: str,
    metric: str,
    state_topic: str,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component=f"{router_component}_{interface_component}",
        metric=metric,
        state_topic_override=state_topic,
    )


def asus_router_network_metrics_client_id(
    device: str,
    router_component: str,
    interface_component: str,
) -> str:
    if not device:
        raise ValueError("device is required")
    if not router_component:
        raise ValueError("router component is required")
    if not interface_component:
        raise ValueError("interface component is required")
    return (
        "homelab-ha-discovery_"
        f"{device}_{router_component}_{interface_component}_network_metrics"
    )


def publish_asus_router_network_discovery(
    device: str,
    router_name: str,
    router_component: str,
    interface_component: str,
    state_topic: str,
    debug: bool = False,
) -> None:
    configs = (
        (
            asus_router_network_metric_identity(
                device,
                router_component,
                interface_component,
                "download_speed",
                state_topic,
            ),
            f"{device} {router_name} {interface_component} Download Speed",
            "{{ value_json['Download Speed'] }}",
        ),
        (
            asus_router_network_metric_identity(
                device,
                router_component,
                interface_component,
                "upload_speed",
                state_topic,
            ),
            f"{device} {router_name} {interface_component} Upload Speed",
            "{{ value_json['Upload Speed'] }}",
        ),
    )
    for identity, name, value_template in configs:
        debug_log(debug, f"publishing discovery config to {identity.discovery_topic}")
        payload = json.dumps(
            sensor_discovery_config(
                identity,
                name=name,
                unit_of_measurement="Mbps",
                state_class="measurement",
                value_template=value_template,
            ),
            separators=(",", ":"),
        )
        publish_mqtt(
            identity.discovery_topic,
            payload,
            default_client_id=asus_router_network_metrics_client_id(
                device,
                router_component,
                interface_component,
            ),
            retain=True,
        )


def publish_asus_router_network_metrics(
    env_files: tuple[str, ...],
    device: str,
    router_name: str,
    dev: str,
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    network_command: str | None = None,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
    debug: bool = False,
) -> int:
    try:
        debug_log(debug, "loading MQTT environment files")
        load_env_files(env_files)
        router_component = router_component_from_name(router_name)
        interface_component = router_interface_component(dev)
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic
            or asus_router_network_metrics_state_topic(
                device,
                router_component,
                interface_component,
            ),
        )
        debug_log(debug, f"router component is {router_component}")
        debug_log(debug, f"interface component is {interface_component}")
        debug_log(debug, f"state topic is {mqtt_topic}")
        debug_log(
            debug,
            f"running SSH network command on {ssh_user}@{ssh_ip}:{ssh_port} "
            f"for {interface_component}",
        )
        network_output = run_asus_router_network(
            ssh_user,
            ssh_ip,
            interface_component,
            ssh_port=ssh_port,
            network_command=network_command,
        )
        debug_log(debug, f"received {len(network_output)} bytes from network command")
        debug_dump(debug, "network command raw output", network_output)
        metrics = parse_asus_router_network_metrics(network_output)
        debug_log(debug, f"parsed network metrics: {metrics}")

        if not publisher_only:
            publish_asus_router_network_discovery(
                device,
                router_name,
                router_component,
                interface_component,
                mqtt_topic,
                debug=debug,
            )

        payload = json.dumps(metrics, separators=(",", ":"))
        debug_log(debug, f"publishing state payload to {mqtt_topic}: {payload}")
        publish_mqtt(
            mqtt_topic,
            payload,
            default_client_id=asus_router_network_metrics_client_id(
                device,
                router_component,
                interface_component,
            ),
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
        "--dev",
        help="ASUS router network interface name, for example eth0.",
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
        "--network-command",
        help=(
            "Remote command that prints sample1/sample2 byte counters or "
            "download_mbps/upload_mbps lines. By default, a /proc/net/dev "
            "sampler is generated for --dev."
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
    if not args.dev:
        parser.error("the following arguments are required: --dev")
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
    if not validate_timer_seconds(args.timer, "--timer"):
        return 1

    next_discovery_publish_at = 0.0 if not args.publisher_only else None

    def publish() -> int:
        nonlocal next_discovery_publish_at
        publish_discovery = (
            next_discovery_publish_at is not None
            and time.monotonic() >= next_discovery_publish_at
        )
        result = publish_asus_router_network_metrics(
            DEFAULT_ENV_FILES,
            args.device,
            args.router_name,
            args.dev,
            args.ssh_user,
            args.ssh_ip,
            ssh_port=args.ssh_port,
            network_command=args.network_command,
            publisher_only=not publish_discovery,
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
