from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery import mqtt as mqtt_module


class FakePublishResult:
    def __init__(self, rc: int = 0) -> None:
        self.rc = rc
        self.wait_count = 0

    def wait_for_publish(self) -> None:
        self.wait_count += 1


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, *, callback_api_version: object, client_id: str) -> None:
        self.callback_api_version = callback_api_version
        self.client_id = client_id
        self.connect_timeout: int | None = None
        self.username_password: tuple[str | None, str | None] | None = None
        self.connect_calls: list[tuple[str, int, int]] = []
        self.loop_start_count = 0
        self.loop_stop_count = 0
        self.disconnect_count = 0
        self.published: list[tuple[str, str, bool]] = []
        FakeClient.instances.append(self)

    def username_pw_set(self, username: str | None, password: str | None) -> None:
        self.username_password = (username, password)

    def connect(self, host: str, port: int, keepalive: int) -> int:
        self.connect_calls.append((host, port, keepalive))
        return 0

    def loop_start(self) -> None:
        self.loop_start_count += 1

    def loop_stop(self) -> None:
        self.loop_stop_count += 1

    def disconnect(self) -> None:
        self.disconnect_count += 1

    def publish(self, topic: str, payload: str, retain: bool = False) -> object:
        self.published.append((topic, payload, retain))
        return FakePublishResult()


def fake_paho_modules() -> dict[str, types.ModuleType]:
    paho = types.ModuleType("paho")
    mqtt_package = types.ModuleType("paho.mqtt")
    client_module = types.ModuleType("paho.mqtt.client")

    class CallbackAPIVersion:
        VERSION2 = object()

    client_module.CallbackAPIVersion = CallbackAPIVersion
    client_module.Client = FakeClient
    client_module.MQTT_ERR_SUCCESS = 0
    mqtt_package.client = client_module
    paho.mqtt = mqtt_package
    return {
        "paho": paho,
        "paho.mqtt": mqtt_package,
        "paho.mqtt.client": client_module,
    }


class MqttPublisherTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeClient.instances = []

    def test_mqtt_publisher_reuses_one_connection_for_multiple_batches(self) -> None:
        env = {
            "HA_MQTT_HOST": "mqtt.example",
            "HA_MQTT_PORT": "1884",
            "HA_MQTT_USERNAME": "user",
            "HA_MQTT_PASSWORD": "password",
            "HA_MQTT_CLIENT_ID": "custom-client",
        }

        with (
            patch.dict(sys.modules, fake_paho_modules()),
            patch.dict(os.environ, env, clear=True),
            redirect_stdout(io.StringIO()),
        ):
            with mqtt_module.MqttPublisher(default_client_id="default") as publisher:
                publisher.publish_many([("topic/a", "1", False)])
                publisher.publish_many(
                    [
                        ("topic/b", "2", True),
                        ("topic/c", "3", False),
                    ]
                )

        self.assertEqual(len(FakeClient.instances), 1)
        client = FakeClient.instances[0]
        self.assertEqual(client.client_id, "custom-client")
        self.assertEqual(client.username_password, ("user", "password"))
        self.assertEqual(
            client.connect_calls,
            [("mqtt.example", 1884, mqtt_module.MQTT_KEEPALIVE_SECONDS)],
        )
        self.assertEqual(client.loop_start_count, 1)
        self.assertEqual(client.loop_stop_count, 1)
        self.assertEqual(client.disconnect_count, 1)
        self.assertEqual(
            client.published,
            [
                ("topic/a", "1", False),
                ("topic/b", "2", True),
                ("topic/c", "3", False),
            ],
        )

    def test_publish_mqtt_many_uses_one_connection_per_call(self) -> None:
        with (
            patch.dict(sys.modules, fake_paho_modules()),
            patch.dict(os.environ, {}, clear=True),
            redirect_stdout(io.StringIO()),
        ):
            mqtt_module.publish_mqtt_many(
                [("topic/a", "1", False)],
                default_client_id="default-a",
            )
            mqtt_module.publish_mqtt_many(
                [("topic/b", "2", True)],
                default_client_id="default-b",
            )

        self.assertEqual(len(FakeClient.instances), 2)
        self.assertEqual(FakeClient.instances[0].client_id, "default-a")
        self.assertEqual(FakeClient.instances[1].client_id, "default-b")
        self.assertEqual(FakeClient.instances[0].loop_start_count, 1)
        self.assertEqual(FakeClient.instances[0].loop_stop_count, 1)
        self.assertEqual(FakeClient.instances[0].disconnect_count, 1)
        self.assertEqual(FakeClient.instances[1].loop_start_count, 1)
        self.assertEqual(FakeClient.instances[1].loop_stop_count, 1)
        self.assertEqual(FakeClient.instances[1].disconnect_count, 1)


if __name__ == "__main__":
    unittest.main()
