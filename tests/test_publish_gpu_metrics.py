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

from homelab_ha_discovery.scripts import publish_gpu_metrics as script


GPU_METRICS = {
    "gpu0": {
        "GPU Card Name": "NVIDIA RTX 4000",
        "GPU Usages": 12.3,
        "Memory Usage": 45.6,
        "Temperature": 61,
    },
    "gpu1": {
        "GPU Card Name": "NVIDIA RTX 5000",
        "GPU Usages": 22.3,
        "Memory Usage": 55.6,
        "Temperature": 62,
    },
}


class FakeMqttPublisher:
    def __init__(self, default_client_id: str) -> None:
        self.default_client_id = default_client_id

    def __enter__(self) -> "FakeMqttPublisher":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        return None


class PublishGpuMetricsTest(unittest.TestCase):
    def test_nvidia_discovery_keeps_existing_ids_and_templates(self) -> None:
        state_topic = script.gpu_state_topic("hpc")

        messages = script.gpu_discovery_messages("hpc", state_topic, GPU_METRICS)

        self.assertEqual(
            [message[0] for message in messages],
            [
                "homeassistant/sensor/homelab_ha_discovery_hpc_gpu0_usage/config",
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_gpu0_memory_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_gpu0_temperature/config"
                ),
                "homeassistant/sensor/homelab_ha_discovery_hpc_gpu1_usage/config",
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_gpu1_memory_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_gpu1_temperature/config"
                ),
            ],
        )
        payloads = [json.loads(message[1]) for message in messages]
        self.assertEqual(payloads[0]["name"], "hpc GPU0 Usage")
        self.assertEqual(payloads[0]["state_topic"], state_topic)
        self.assertEqual(
            payloads[0]["value_template"],
            "{{ value_json['gpu0']['GPU Usages'] }}",
        )
        self.assertTrue(all(message[2] for message in messages))

    def test_amd_rocm_discovery_uses_collector_specific_ids(self) -> None:
        state_topic = script.gpu_state_topic("hpc", collector="amd_rocm")

        messages = script.gpu_discovery_messages(
            "hpc",
            state_topic,
            {"gpu0": GPU_METRICS["gpu0"]},
            collector="amd_rocm",
        )

        self.assertEqual(
            [message[0] for message in messages],
            [
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_amd_rocm_gpu0_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_amd_rocm_gpu0_memory_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_amd_rocm_gpu0_temperature/config"
                ),
            ],
        )
        payloads = [json.loads(message[1]) for message in messages]
        self.assertEqual(payloads[0]["name"], "hpc AMD ROCm GPU0 Usage")
        self.assertEqual(
            payloads[0]["state_topic"],
            "homelab-ha-discovery/gpu/amd_rocm/usages/hpc",
        )
        self.assertEqual(
            payloads[0]["value_template"],
            "{{ value_json['gpu0']['GPU Usages'] }}",
        )

    def test_publish_multiple_selected_gpus_in_one_state_payload(self) -> None:
        with (
            patch.object(script, "load_env_files"),
            patch.object(script, "collect_gpu_metrics", return_value=GPU_METRICS),
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
        ):
            result = script.publish_gpu_metrics(
                (),
                "hpc",
                gpu_indexes=(0, 1),
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        messages = publish_mqtt_many.call_args.args[0]
        self.assertEqual(
            messages,
            [
                (
                    "homelab-ha-discovery/gpu/usages/hpc",
                    json.dumps(GPU_METRICS, separators=(",", ":")),
                    False,
                )
            ],
        )
        self.assertEqual(
            publish_mqtt_many.call_args.kwargs["default_client_id"],
            "homelab-ha-discovery_hpc_gpu_metrics",
        )

    def test_publish_single_gpu_keeps_indexed_state_topic(self) -> None:
        with (
            patch.object(script, "load_env_files"),
            patch.object(script, "collect_gpu_metrics", return_value=GPU_METRICS),
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
        ):
            result = script.publish_gpu_metrics(
                (),
                "hpc",
                gpu_index=1,
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        messages = publish_mqtt_many.call_args.args[0]
        self.assertEqual(messages[0][0], "homelab-ha-discovery/gpu/usages/hpc/gpu1")
        self.assertEqual(json.loads(messages[0][1]), {"gpu1": GPU_METRICS["gpu1"]})

    def test_publish_amd_rocm_uses_collector_specific_topic_and_client(self) -> None:
        with (
            patch.object(script, "load_env_files"),
            patch.object(script, "collect_gpu_metrics", return_value=GPU_METRICS),
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
        ):
            result = script.publish_gpu_metrics(
                (),
                "hpc",
                gpu_indexes=(0,),
                collector="amd_rocm",
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        messages = publish_mqtt_many.call_args.args[0]
        self.assertEqual(
            messages[0][0],
            "homelab-ha-discovery/gpu/amd_rocm/usages/hpc/gpu0",
        )
        self.assertEqual(
            publish_mqtt_many.call_args.kwargs["default_client_id"],
            "homelab-ha-discovery_hpc_amd_rocm_gpu_metrics",
        )

    def test_timer_passes_repeated_gpu_indexes(self) -> None:
        def fake_run_publish_timer(timer: float | None, publish: object) -> int:
            self.assertEqual(timer, 5.0)
            self.assertEqual(publish(), 0)
            return 0

        with (
            patch.object(
                script,
                "run_publish_timer",
                side_effect=fake_run_publish_timer,
            ),
            patch.object(script, "load_env_files"),
            patch.object(script, "MqttPublisher", FakeMqttPublisher),
            patch.object(script, "publish_gpu_metrics", return_value=0) as publish,
        ):
            result = script.main(
                [
                    "--ha-device-id",
                    "hpc",
                    "--collector",
                    "amd_rocm",
                    "--gpu",
                    "0",
                    "--gpu",
                    "1",
                    "--timer",
                    "5.0",
                ]
            )

        self.assertEqual(result, 0)
        self.assertEqual(publish.call_args.kwargs["collector"], "amd_rocm")
        self.assertEqual(publish.call_args.kwargs["gpu_indexes"], (0, 1))

    def test_gpu_indexes_and_gpu_index_are_mutually_exclusive(self) -> None:
        with (
            patch.object(script, "load_env_files"),
            patch.object(script, "collect_gpu_metrics", return_value=GPU_METRICS),
            patch.object(script, "publish_mqtt_many"),
            redirect_stderr(io.StringIO()),
        ):
            result = script.publish_gpu_metrics(
                (),
                "hpc",
                gpu_index=0,
                gpu_indexes=(1,),
            )

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
