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

from homelab_ha_discovery.collectors.docker_containers import (
    DockerContainerInfo,
    DockerContainerSample,
    DockerContainerStats,
)
from homelab_ha_discovery.scripts import publish_docker_container_metrics as script


class PublishDockerContainerMetricsTest(unittest.TestCase):
    def make_sample(
        self,
        *,
        timestamp: float,
        rx_bytes: float,
        tx_bytes: float,
    ) -> DockerContainerSample:
        container_id = "abc123def456789"
        return DockerContainerSample(
            containers={
                container_id: DockerContainerInfo(
                    container_id=container_id,
                    name="plex",
                    component="plex",
                    state="running",
                    health="healthy",
                    restart_count=2,
                    labels={},
                )
            },
            stats={
                container_id: DockerContainerStats(
                    cpu_usage_percent=2.318,
                    memory_usage_bytes=512_400_000.0,
                    memory_limit_bytes=8_192_000_000.0,
                    memory_usage_percent=6.25,
                    network_rx_bytes=rx_bytes,
                    network_tx_bytes=tx_bytes,
                )
            },
            timestamp=timestamp,
        )

    def test_discovery_topics_include_docker_component(self) -> None:
        state_topic = script.docker_metrics_state_topic("hpc", "plex")

        with patch.object(script, "publish_mqtt_many") as publish_mqtt_many:
            script.publish_docker_container_discovery(
                "hpc",
                "plex",
                "plex",
                state_topic,
            )

        messages = publish_mqtt_many.call_args.args[0]
        self.assertEqual(
            [message[0] for message in messages],
            [
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_state/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_health/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_restart_count/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_cpu_usage/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_memory_usage_mb/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_memory_limit_mb/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_memory_usage_percent/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_download_speed/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_docker_plex_upload_speed/config"
                ),
            ],
        )
        payloads = [
            json.loads(message[1])
            for message in messages
        ]
        self.assertEqual(payloads[0]["name"], "hpc Docker plex State")
        self.assertEqual(payloads[0]["state_topic"], state_topic)
        self.assertEqual(payloads[0]["value_template"], "{{ value_json['State'] }}")
        self.assertEqual(payloads[3]["unit_of_measurement"], "%")
        self.assertEqual(payloads[7]["unit_of_measurement"], "Mbps")
        self.assertTrue(all(message[2] for message in messages))
        self.assertEqual(
            publish_mqtt_many.call_args.kwargs["default_client_id"],
            "homelab-ha-discovery_hpc_docker_plex_metrics",
        )

    def test_discovery_config_includes_expire_after_when_set(self) -> None:
        state_topic = script.docker_metrics_state_topic("hpc", "plex")

        with patch.object(script, "publish_mqtt_many") as publish_mqtt_many:
            script.publish_docker_container_discovery(
                "hpc",
                "plex",
                "plex",
                state_topic,
                expire_after=180.0,
            )

        messages = publish_mqtt_many.call_args.args[0]
        payloads = [
            json.loads(message[1])
            for message in messages
        ]
        self.assertTrue(all(payload["expire_after"] == 180 for payload in payloads))

    def test_effective_expire_after_defaults_to_timer_times_three(self) -> None:
        self.assertEqual(script.effective_expire_after(None, 60.0), 180.0)
        self.assertIsNone(script.effective_expire_after(None, None))
        self.assertIsNone(script.effective_expire_after(0.0, 60.0))
        self.assertEqual(script.effective_expire_after(30.0, 60.0), 30.0)

    def test_publish_state_payload_per_container(self) -> None:
        with (
            patch.object(script, "load_env_files"),
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
        ):
            result = script.publish_docker_metrics_from_samples(
                (),
                "hpc",
                self.make_sample(timestamp=1.0, rx_bytes=1000.0, tx_bytes=2000.0),
                self.make_sample(timestamp=2.0, rx_bytes=1125.0, tx_bytes=127000.0),
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        publish_mqtt_many.assert_called_once()
        messages = publish_mqtt_many.call_args.args[0]
        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages[0][0],
            "homelab-ha-discovery/hpc/docker/plex/metrics",
        )
        self.assertEqual(
            json.loads(messages[0][1]),
            {
                "State": "running",
                "Health": "healthy",
                "Restart Count": 2,
                "CPU Usage": 2.318,
                "Memory Usage MB": 512.4,
                "Memory Limit MB": 8192.0,
                "Memory Usage Percent": 6.25,
                "Download Speed": 0.001,
                "Upload Speed": 1.0,
            },
        )
        self.assertFalse(messages[0][2])
        self.assertEqual(
            publish_mqtt_many.call_args.kwargs["default_client_id"],
            "homelab-ha-discovery_hpc_docker_metrics",
        )

    def test_discovery_components_limits_discovery_not_state_publish(self) -> None:
        plex_id = "abc123def456789"
        nginx_id = "def456abc123789"
        containers = {
            plex_id: DockerContainerInfo(
                container_id=plex_id,
                name="plex",
                component="plex",
                state="running",
                health="healthy",
                restart_count=0,
                labels={},
            ),
            nginx_id: DockerContainerInfo(
                container_id=nginx_id,
                name="nginx",
                component="nginx",
                state="running",
                health="none",
                restart_count=0,
                labels={},
            ),
        }

        def sample(timestamp: float, offset: float) -> DockerContainerSample:
            return DockerContainerSample(
                containers=containers,
                stats={
                    plex_id: DockerContainerStats(
                        cpu_usage_percent=1.0,
                        memory_usage_bytes=1_000_000.0,
                        memory_limit_bytes=10_000_000.0,
                        memory_usage_percent=10.0,
                        network_rx_bytes=1000.0 + offset,
                        network_tx_bytes=2000.0 + offset,
                    ),
                    nginx_id: DockerContainerStats(
                        cpu_usage_percent=1.0,
                        memory_usage_bytes=1_000_000.0,
                        memory_limit_bytes=10_000_000.0,
                        memory_usage_percent=10.0,
                        network_rx_bytes=3000.0 + offset,
                        network_tx_bytes=4000.0 + offset,
                    ),
                },
                timestamp=timestamp,
            )

        with (
            patch.object(script, "load_env_files"),
            patch.object(script, "publish_mqtt_many") as publish_mqtt_many,
        ):
            result = script.publish_docker_metrics_from_samples(
                (),
                "hpc",
                sample(1.0, 0.0),
                sample(2.0, 1000.0),
                discovery_components={"nginx"},
            )

        self.assertEqual(result, 0)
        messages = publish_mqtt_many.call_args.args[0]
        topics = [message[0] for message in messages]
        discovery_topics = [
            topic
            for topic in topics
            if topic.startswith("homeassistant/sensor/")
        ]
        state_topics = [
            topic
            for topic in topics
            if not topic.startswith("homeassistant/sensor/")
        ]
        self.assertTrue(discovery_topics)
        self.assertTrue(all("_docker_nginx_" in topic for topic in discovery_topics))
        self.assertEqual(
            state_topics,
            [
                "homelab-ha-discovery/hpc/docker/nginx/metrics",
                "homelab-ha-discovery/hpc/docker/plex/metrics",
            ],
        )

    def test_debug_prints_sample_summary(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(script, "load_env_files"),
            patch.object(script, "publish_mqtt_many"),
            redirect_stderr(stderr),
        ):
            result = script.publish_docker_metrics_from_samples(
                (),
                "hpc",
                self.make_sample(timestamp=1.0, rx_bytes=1000.0, tx_bytes=2000.0),
                self.make_sample(timestamp=2.0, rx_bytes=1125.0, tx_bytes=127000.0),
                publisher_only=True,
                debug=True,
        )

        self.assertEqual(result, 0)
        self.assertRegex(
            stderr.getvalue(),
            r"DEBUG: \d{4}-\d{2}-\d{2}T.* previous sample: included_containers=1",
        )
        self.assertRegex(
            stderr.getvalue(),
            r"DEBUG: \d{4}-\d{2}-\d{2}T.* calculated Docker metrics: metrics=1",
        )


if __name__ == "__main__":
    unittest.main()
