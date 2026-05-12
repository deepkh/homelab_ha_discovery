from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.scripts import publish_frigate_metrics as script


FRIGATE_METRICS = {
    "system": {
        "CPU Usage": 12.346,
        "Memory Usage": 45.679,
    },
    "cameras": {
        "front door": {
            "Camera FPS": 5.0,
            "Process FPS": 4.5,
            "Skipped FPS": 0.0,
            "Detection FPS": 3.25,
        },
    },
    "detectors": {
        "coral": {
            "Inference Speed": 0.011,
        },
    },
    "gpus": {
        "nvidia 0": {
            "GPU Usage": 33.333,
            "Memory Usage": 55.556,
        },
    },
    "storage": {
        "/media/frigate/recordings": {
            "Free GB": 1.235,
            "Used GB": 9.877,
        },
    },
}


class PublishFrigateMetricsTest(unittest.TestCase):
    def test_discovery_topics_and_value_templates(self) -> None:
        state_topic = script.frigate_metrics_state_topic("hpc")

        messages = script.frigate_discovery_messages(
            "hpc",
            state_topic,
            FRIGATE_METRICS,
        )

        self.assertEqual(
            [message[0] for message in messages],
            [
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_system_cpu_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_system_memory_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_camera_front_door_camera_fps/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_camera_front_door_process_fps/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_camera_front_door_skipped_fps/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_camera_front_door_detection_fps/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_detector_coral_inference_speed/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_gpu_nvidia_0_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_gpu_nvidia_0_memory_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_storage_media_frigate_recordings_free_gb/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_frigate_storage_media_frigate_recordings_used_gb/config"
                ),
            ],
        )
        payloads = [json.loads(message[1]) for message in messages]
        self.assertEqual(payloads[0]["state_topic"], state_topic)
        self.assertEqual(payloads[0]["unit_of_measurement"], "%")
        self.assertEqual(
            payloads[2]["value_template"],
            "{{ value_json['cameras']['front door']['Camera FPS'] }}",
        )
        self.assertEqual(payloads[2]["unit_of_measurement"], "fps")
        self.assertEqual(payloads[6]["unit_of_measurement"], "s")
        self.assertEqual(payloads[9]["unit_of_measurement"], "GB")
        self.assertTrue(all(message[2] for message in messages))

    def test_discovery_config_includes_expire_after_when_set(self) -> None:
        messages = script.frigate_discovery_messages(
            "hpc",
            script.frigate_metrics_state_topic("hpc"),
            FRIGATE_METRICS,
            expire_after=30.2,
        )

        payloads = [json.loads(message[1]) for message in messages]
        self.assertTrue(all(payload["expire_after"] == 31 for payload in payloads))

    def test_publish_state_payload_to_shared_topic(self) -> None:
        with (
            patch.object(script, "read_frigate_metrics", return_value=FRIGATE_METRICS),
            patch.object(script, "load_env_files"),
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
        ):
            result = script.publish_frigate_metrics(
                (),
                "hpc",
                url="http://127.0.0.1:5000/api/metrics",
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        publish_mqtt_many.assert_called_once()
        messages = publish_mqtt_many.call_args.args[0]
        self.assertEqual(
            messages,
            [
                (
                    "homelab-ha-discovery/frigate/metrics/hpc",
                    json.dumps(FRIGATE_METRICS, separators=(",", ":")),
                    False,
                )
            ],
        )
        self.assertEqual(
            publish_mqtt_many.call_args.kwargs["default_client_id"],
            "homelab-ha-discovery_hpc_frigate_metrics",
        )

    def test_publish_batches_discovery_and_state(self) -> None:
        with (
            patch.object(script, "read_frigate_metrics", return_value=FRIGATE_METRICS),
            patch.object(script, "load_env_files"),
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
        ):
            result = script.publish_frigate_metrics((), "hpc")

        self.assertEqual(result, 0)
        messages = publish_mqtt_many.call_args.args[0]
        self.assertEqual(len(messages), 12)
        self.assertTrue(messages[0][0].startswith("homeassistant/sensor/"))
        self.assertTrue(messages[0][2])
        self.assertEqual(messages[-1][0], "homelab-ha-discovery/frigate/metrics/hpc")
        self.assertFalse(messages[-1][2])

    def test_publish_failure_before_mqtt_publish(self) -> None:
        with (
            patch.object(
                script,
                "read_frigate_metrics",
                side_effect=ValueError("missing Frigate metric family"),
            ),
            patch.object(script, "load_env_files") as load_env_files,
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
            redirect_stderr(io.StringIO()),
        ):
            result = script.publish_frigate_metrics((), "hpc")

        self.assertEqual(result, 1)
        load_env_files.assert_not_called()
        publish_mqtt_many.assert_not_called()

    def test_timer_publish_discovery_config_republishes_when_due(self) -> None:
        def fake_run_publish_timer(timer: float | None, publish: object) -> int:
            self.assertEqual(timer, 10.0)
            self.assertEqual(publish(), 0)
            self.assertEqual(publish(), 0)
            return 0

        with (
            patch.object(
                script,
                "run_publish_timer",
                side_effect=fake_run_publish_timer,
            ),
            patch.object(script, "publish_frigate_metrics", return_value=0) as publish,
            patch.object(script.time, "monotonic", side_effect=[1.0, 1.0, 62.0, 62.0]),
        ):
            result = script.main(
                [
                    "--ha-device-id",
                    "hpc",
                    "--timer",
                    "10.0",
                    "--timer-publish-discovery-config",
                    "60.0",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(publish.call_count, 2)
        self.assertFalse(publish.call_args_list[0].kwargs["publisher_only"])
        self.assertFalse(publish.call_args_list[1].kwargs["publisher_only"])
        self.assertEqual(publish.call_args_list[0].kwargs["expire_after"], 30.0)

    def test_timer_publisher_only_skips_discovery(self) -> None:
        def fake_run_publish_timer(_timer: float | None, publish: object) -> int:
            self.assertEqual(publish(), 0)
            return 0

        with (
            patch.object(
                script,
                "run_publish_timer",
                side_effect=fake_run_publish_timer,
            ),
            patch.object(script, "publish_frigate_metrics", return_value=0) as publish,
        ):
            result = script.main(
                [
                    "--ha-device-id",
                    "hpc",
                    "--timer",
                    "10.0",
                    "--publisher-only",
                ]
            )

        self.assertEqual(result, 0)
        self.assertTrue(publish.call_args.kwargs["publisher_only"])

    def test_timer_publish_discovery_config_requires_timer(self) -> None:
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            script.main(
                [
                    "--ha-device-id",
                    "hpc",
                    "--timer-publish-discovery-config",
                    "60.0",
                ]
            )


if __name__ == "__main__":
    unittest.main()
