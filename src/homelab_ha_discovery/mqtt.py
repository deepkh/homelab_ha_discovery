"""Publish JSON payloads to MQTT."""

from __future__ import annotations

import os
import socket
import sys
from typing import Any, Iterable


DEFAULT_MQTT_HOST = "mqtt-server-ip"
DEFAULT_MQTT_PORT = 1883
MQTT_KEEPALIVE_SECONDS = 60
MQTT_CONNECT_TIMEOUT_SECONDS = 10
MqttMessage = tuple[str, str, bool]


def publish_mqtt(
    topic: str,
    payload: str,
    default_client_id: str = "homelab-ha-discovery",
    retain: bool = False,
) -> None:
    publish_mqtt_many(
        ((topic, payload, retain),),
        default_client_id=default_client_id,
    )


def publish_mqtt_many(
    messages: Iterable[MqttMessage],
    default_client_id: str = "homelab-ha-discovery",
) -> None:
    message_list = list(messages)
    if not message_list:
        return

    with MqttPublisher(default_client_id=default_client_id) as publisher:
        publisher.publish_many(message_list)


class MqttPublisher:
    """Reusable MQTT publisher for long-running processes."""

    def __init__(self, default_client_id: str = "homelab-ha-discovery") -> None:
        self.default_client_id = default_client_id
        self.host = DEFAULT_MQTT_HOST
        self.port = DEFAULT_MQTT_PORT
        self.username: str | None = None
        self.password: str | None = None
        self.client_id = default_client_id
        self._mqtt: Any | None = None
        self._client: Any | None = None
        self._loop_started = False

    def __enter__(self) -> "MqttPublisher":
        import paho.mqtt.client as mqtt

        self._mqtt = mqtt
        self.host = os.environ.get("HA_MQTT_HOST", DEFAULT_MQTT_HOST)
        self.port = int(os.environ.get("HA_MQTT_PORT", DEFAULT_MQTT_PORT))
        self.username = os.environ.get("HA_MQTT_USERNAME")
        self.password = os.environ.get("HA_MQTT_PASSWORD")
        self.client_id = os.environ.get("HA_MQTT_CLIENT_ID", self.default_client_id)

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
        )
        client.connect_timeout = MQTT_CONNECT_TIMEOUT_SECONDS
        if self.username or self.password:
            if not self.username:
                raise ValueError(
                    "HA_MQTT_USERNAME is required when HA_MQTT_PASSWORD is set"
                )
            client.username_pw_set(self.username, self.password)

        try:
            connect_result = client.connect(
                self.host,
                self.port,
                keepalive=MQTT_KEEPALIVE_SECONDS,
            )
        except ConnectionRefusedError as exc:
            print(
                "MQTT TCP connection refused: "
                f"attempted={self.host}:{self.port}, "
                f"default_host={DEFAULT_MQTT_HOST}. "
                "Check that the broker is listening on this host/port and that "
                "HA_MQTT_HOST/HA_MQTT_PORT are exported correctly.",
                file=sys.stderr,
            )
            raise exc
        except socket.gaierror as exc:
            print(
                f"MQTT host lookup failed: host={self.host}, error={exc}",
                file=sys.stderr,
            )
            raise
        except TimeoutError as exc:
            print(
                f"MQTT connection timed out: attempted={self.host}:{self.port}",
                file=sys.stderr,
            )
            raise exc
        except OSError as exc:
            print(
                f"MQTT connection failed: attempted={self.host}:{self.port}, "
                f"error={exc}",
                file=sys.stderr,
            )
            raise

        if connect_result != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT connect failed, return code: {connect_result}")

        self._client = client
        try:
            client.loop_start()
            self._loop_started = True
        except Exception:
            client.disconnect()
            self._client = None
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        if self._client is None:
            return
        if self._loop_started:
            self._client.loop_stop()
        self._client.disconnect()
        self._client = None
        self._loop_started = False

    def publish_many(self, messages: Iterable[MqttMessage]) -> None:
        message_list = list(messages)
        if not message_list:
            return
        if self._client is None or self._mqtt is None:
            raise RuntimeError("MQTT publisher is not connected")

        try:
            for topic, payload, retain in message_list:
                print(
                    "MQTT Publish: "
                    f"host={self.host}, "
                    f"port={self.port} , "
                    f"topic={topic}, "
                    f"retain={retain}, "
                    f"username_set={bool(self.username)}, "
                    f"password_set={bool(self.password)}",
                )
                print("MQTT Payload: ")
                print(payload)
                publish_result = self._client.publish(topic, payload, retain=retain)
                publish_result.wait_for_publish()
                if publish_result.rc != self._mqtt.MQTT_ERR_SUCCESS:
                    raise RuntimeError(
                        f"MQTT publish failed, return code: {publish_result.rc}"
                    )
        except ConnectionRefusedError:
            print(f"Connection refused by MQTT host: {self.host}", file=sys.stderr)
            raise
