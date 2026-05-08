"""Publish JSON payloads to MQTT."""

from __future__ import annotations

import os
import socket
import sys


DEFAULT_MQTT_HOST = "mqtt.netsync.tv"
DEFAULT_MQTT_PORT = 1833
MQTT_KEEPALIVE_SECONDS = 60
MQTT_CONNECT_TIMEOUT_SECONDS = 10


def publish_mqtt(
    topic: str,
    payload: str,
    default_client_id: str = "homelab-mqtt-monitor",
) -> None:
    import paho.mqtt.client as mqtt

    host = os.environ.get("HA_MQTT_HOST", DEFAULT_MQTT_HOST)
    port = int(os.environ.get("HA_MQTT_PORT", DEFAULT_MQTT_PORT))
    username = os.environ.get("HA_MQTT_USERNAME")
    password = os.environ.get("HA_MQTT_PASSWORD")
    client_id = os.environ.get("HA_MQTT_CLIENT_ID", default_client_id)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
    )
    client.connect_timeout = MQTT_CONNECT_TIMEOUT_SECONDS
    if username or password:
        if not username:
            raise ValueError("HA_MQTT_USERNAME is required when HA_MQTT_PASSWORD is set")
        client.username_pw_set(username, password)

    print(
        "MQTT Publish: "
        f"host={host}, "
        f"port={port} , "
        f"topic={topic}, "
        f"username_set={bool(username)}, "
        f"password_set={bool(password)}",
    )
    print("MQTT Payload: ")
    print(payload)

    try:
        connect_result = client.connect(host, port, keepalive=MQTT_KEEPALIVE_SECONDS)
    except ConnectionRefusedError as exc:
        print(
            "MQTT TCP connection refused: "
            f"attempted={host}:{port}, default_host={DEFAULT_MQTT_HOST}. "
            "Check that the broker is listening on this host/port and that "
            "HA_MQTT_HOST/HA_MQTT_PORT are exported correctly.",
            file=sys.stderr,
        )
        raise exc
    except socket.gaierror as exc:
        print(f"MQTT host lookup failed: host={host}, error={exc}", file=sys.stderr)
        raise
    except TimeoutError as exc:
        print(f"MQTT connection timed out: attempted={host}:{port}", file=sys.stderr)
        raise exc
    except OSError as exc:
        print(
            f"MQTT connection failed: attempted={host}:{port}, error={exc}",
            file=sys.stderr,
        )
        raise

    if connect_result != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"MQTT connect failed, return code: {connect_result}")

    try:
        client.loop_start()
        publish_result = client.publish(topic, payload)
        publish_result.wait_for_publish()
        if publish_result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed, return code: {publish_result.rc}")
    except ConnectionRefusedError:
        print(f"Connection refused by MQTT host: {DEFAULT_MQTT_HOST}", file=sys.stderr)
        raise
    finally:
        client.loop_stop()
        client.disconnect()
