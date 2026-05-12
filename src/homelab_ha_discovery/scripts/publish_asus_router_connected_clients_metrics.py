"""Publish ASUS router connected-client metrics collected over SSH."""

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
    DEFAULT_CLIENT_LIST_COMMAND,
    DEFAULT_SSH_PORT,
    asus_router_connected_clients_debug_lines,
    parse_asus_router_connected_clients,
    run_asus_router_client_list,
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
from homelab_ha_discovery.mqtt import MqttMessage, MqttPublisher, publish_mqtt_many
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


def asus_router_connected_clients_state_topic(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"{mqtt_topic_prefix()}/{component}/connected_clients/metrics/{device}"


def asus_router_connected_clients_identity(
    device: str,
    component: str,
    state_topic: str,
) -> MetricIdentity:
    return MetricIdentity(
        host=device,
        component=component,
        metric="connected_clients",
        state_topic_override=state_topic,
    )


def asus_router_connected_clients_client_id(device: str, component: str) -> str:
    if not device:
        raise ValueError("device is required")
    if not component:
        raise ValueError("component is required")
    return f"homelab-ha-discovery_{device}_{component}_connected_clients_metrics"


def publish_asus_router_connected_clients_discovery(
    device: str,
    router_name: str,
    component: str,
    state_topic: str,
    debug: bool = False,
    expire_after: float | None = None,
) -> None:
    messages = asus_router_connected_clients_discovery_messages(
        device,
        router_name,
        component,
        state_topic,
        expire_after=expire_after,
        debug=debug,
    )
    publish_mqtt_many(
        messages,
        default_client_id=asus_router_connected_clients_client_id(device, component),
    )


def asus_router_connected_clients_discovery_messages(
    device: str,
    router_name: str,
    component: str,
    state_topic: str,
    expire_after: float | None = None,
    debug: bool = False,
) -> list[MqttMessage]:
    identity = asus_router_connected_clients_identity(device, component, state_topic)
    debug_log(debug, f"queueing discovery config to {identity.discovery_topic}")
    payload = json.dumps(
        sensor_discovery_config(
            identity,
            name=f"{device} {router_name} Connected Clients",
            unit_of_measurement="clients",
            state_class="measurement",
            value_template="{{ value_json | count }}",
            expire_after=expire_after,
        ),
        separators=(",", ":"),
    )
    return [(identity.discovery_topic, payload, True)]


def publish_asus_router_connected_clients_metrics(
    env_files: tuple[str, ...],
    device: str,
    router_name: str,
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    client_list_command: str = DEFAULT_CLIENT_LIST_COMMAND,
    default_mqtt_topic: str | None = None,
    publisher_only: bool = False,
    debug: bool = False,
    expire_after: float | None = None,
    mqtt_publisher: MqttPublisher | None = None,
) -> int:
    try:
        if mqtt_publisher is None:
            debug_log(debug, "loading MQTT environment files")
            load_env_files(env_files)
        else:
            debug_log(debug, "using existing MQTT publisher")
        component = router_component_from_name(router_name)
        mqtt_topic = os.environ.get(
            "MQTT_TOPIC",
            default_mqtt_topic
            or asus_router_connected_clients_state_topic(device, component),
        )
        debug_log(debug, f"router component is {component}")
        debug_log(debug, f"state topic is {mqtt_topic}")
        debug_log(
            debug,
            f"running SSH client-list command on {ssh_user}@{ssh_ip}:{ssh_port}: "
            f"{client_list_command}",
        )
        client_list_output = run_asus_router_client_list(
            ssh_user,
            ssh_ip,
            ssh_port=ssh_port,
            client_list_command=client_list_command,
        )
        debug_log(
            debug,
            f"received {len(client_list_output)} bytes from client-list command",
        )
        debug_dump(debug, "client-list command raw output", client_list_output)
        for line in asus_router_connected_clients_debug_lines(client_list_output):
            debug_log(debug, f"parser: {line}")
        clients = parse_asus_router_connected_clients(client_list_output)
        debug_log(debug, f"parsed connected clients: {len(clients)}")

        mqtt_messages: list[MqttMessage] = []
        if not publisher_only:
            mqtt_messages.extend(
                asus_router_connected_clients_discovery_messages(
                    device,
                    router_name,
                    component,
                    mqtt_topic,
                    expire_after=expire_after,
                    debug=debug,
                )
            )

        payload = json.dumps(clients, separators=(",", ":"))
        debug_log(debug, f"queueing state payload to {mqtt_topic}: {payload}")
        mqtt_messages.append((mqtt_topic, payload, False))
        debug_log(
            debug,
            f"publishing {len(mqtt_messages)} MQTT message(s) in one connection",
        )
        if mqtt_publisher is None:
            publish_mqtt_many(
                mqtt_messages,
                default_client_id=asus_router_connected_clients_client_id(
                    device,
                    component,
                ),
            )
        else:
            mqtt_publisher.publish_many(mqtt_messages)
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
        "--client-list-command",
        default=DEFAULT_CLIENT_LIST_COMMAND,
        help=(
            "Remote command that prints dnsmasq leases, "
            "---END_LEASES---, and /tmp/clientlist.json. "
            f"Default: {DEFAULT_CLIENT_LIST_COMMAND!r}"
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
    if not validate_timer_seconds(args.timer, "--timer"):
        return 1
    if not validate_expire_after_seconds(args.expire_after):
        return 1

    expire_after = effective_expire_after(args.expire_after, args.timer)

    next_discovery_publish_at = 0.0 if not args.publisher_only else None

    def publish(mqtt_publisher: MqttPublisher | None = None) -> int:
        nonlocal next_discovery_publish_at
        publish_discovery = (
            next_discovery_publish_at is not None
            and time.monotonic() >= next_discovery_publish_at
        )
        result = publish_asus_router_connected_clients_metrics(
            DEFAULT_ENV_FILES,
            args.device,
            args.router_name,
            args.ssh_user,
            args.ssh_ip,
            ssh_port=args.ssh_port,
            client_list_command=args.client_list_command,
            publisher_only=not publish_discovery,
            expire_after=expire_after,
            debug=args.debug,
            mqtt_publisher=mqtt_publisher,
        )
        if result == 0 and publish_discovery:
            if args.timer_publish_discovery_config is None:
                next_discovery_publish_at = None
            else:
                next_discovery_publish_at = (
                    time.monotonic() + args.timer_publish_discovery_config
                )
        return result

    if args.timer is not None:
        try:
            load_env_files(DEFAULT_ENV_FILES)
            component = router_component_from_name(args.router_name)
            with MqttPublisher(
                default_client_id=asus_router_connected_clients_client_id(
                    args.device,
                    component,
                ),
            ) as mqtt_publisher:
                return run_publish_timer(args.timer, lambda: publish(mqtt_publisher))
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    return run_publish_timer(args.timer, publish)


if __name__ == "__main__":
    raise SystemExit(main())
