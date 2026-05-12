from __future__ import annotations

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
from homelab_ha_discovery.collectors.network_linux import NetworkCounterSample
from homelab_ha_discovery.scripts import publish_cpu_metrics
from homelab_ha_discovery.scripts import publish_docker_container_metrics
from homelab_ha_discovery.scripts import publish_network_metrics


class FakePersistentPublisher:
    instances: list["FakePersistentPublisher"] = []

    def __init__(self, default_client_id: str) -> None:
        self.default_client_id = default_client_id
        self.enter_count = 0
        self.exit_count = 0
        self.batches: list[list[tuple[str, str, bool]]] = []
        FakePersistentPublisher.instances.append(self)

    def __enter__(self) -> "FakePersistentPublisher":
        self.enter_count += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        self.exit_count += 1

    def publish_many(self, messages: object) -> None:
        self.batches.append(list(messages))


class PersistentTimerPublisherTest(unittest.TestCase):
    def setUp(self) -> None:
        FakePersistentPublisher.instances = []

    def docker_sample(
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

    def test_simple_timer_publisher_uses_persistent_mqtt_publisher(self) -> None:
        def fake_run_publish_timer(timer: float | None, publish: object) -> int:
            self.assertEqual(timer, 5.0)
            self.assertEqual(publish(), 0)
            self.assertEqual(publish(), 0)
            return 0

        with (
            patch.object(publish_cpu_metrics, "load_env_files"),
            patch.object(
                publish_cpu_metrics,
                "MqttPublisher",
                FakePersistentPublisher,
            ),
            patch.object(
                publish_cpu_metrics,
                "run_publish_timer",
                side_effect=fake_run_publish_timer,
            ),
            patch.object(publish_cpu_metrics, "run_top", return_value="top output"),
            patch.object(
                publish_cpu_metrics,
                "parse_cpu_usage",
                return_value=12.3,
            ),
            patch.object(
                publish_cpu_metrics,
                "run_sensors",
                return_value="sensors output",
            ),
            patch.object(
                publish_cpu_metrics,
                "parse_cpu_temperature",
                return_value=45.0,
            ),
            patch.object(publish_cpu_metrics, "publish_mqtt_many") as publish_many,
        ):
            result = publish_cpu_metrics.main(
                ["--ha-device-id", "hpc", "--timer", "5.0"]
            )

        self.assertEqual(result, 0)
        publish_many.assert_not_called()
        self.assertEqual(len(FakePersistentPublisher.instances), 1)
        publisher = FakePersistentPublisher.instances[0]
        self.assertEqual(
            publisher.default_client_id,
            "homelab-ha-discovery_hpc_cpu_metrics",
        )
        self.assertEqual(publisher.enter_count, 1)
        self.assertEqual(publisher.exit_count, 1)
        self.assertEqual(len(publisher.batches), 2)
        self.assertEqual(len(publisher.batches[0]), 3)
        self.assertEqual(len(publisher.batches[1]), 1)
        self.assertEqual(
            json.loads(publisher.batches[0][-1][1]),
            {"CPU Usages": 12.3, "Temperature": 45.0},
        )

    def test_network_timer_publishes_intervals_through_one_publisher(self) -> None:
        samples = [
            NetworkCounterSample(bytes_recv=1000, bytes_sent=2000, timestamp=1.0),
            NetworkCounterSample(bytes_recv=1125, bytes_sent=127000, timestamp=2.0),
            NetworkCounterSample(bytes_recv=1250, bytes_sent=252000, timestamp=3.0),
        ]

        with (
            patch.object(publish_network_metrics, "load_env_files"),
            patch.object(
                publish_network_metrics,
                "MqttPublisher",
                FakePersistentPublisher,
            ),
            patch.object(
                publish_network_metrics,
                "read_network_counter_sample",
                side_effect=samples,
            ),
            patch.object(
                publish_network_metrics.time,
                "sleep",
                side_effect=[None, None, KeyboardInterrupt],
            ),
            patch.object(publish_network_metrics, "publish_mqtt_many") as publish_many,
        ):
            result = publish_network_metrics.run_network_publish_timer(
                1.0,
                "hpc",
                "ppp0",
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        publish_many.assert_not_called()
        self.assertEqual(len(FakePersistentPublisher.instances), 1)
        publisher = FakePersistentPublisher.instances[0]
        self.assertEqual(
            publisher.default_client_id,
            "homelab-ha-discovery_hpc_ppp0_metrics",
        )
        self.assertEqual(publisher.enter_count, 1)
        self.assertEqual(publisher.exit_count, 1)
        self.assertEqual(len(publisher.batches), 2)
        self.assertTrue(all(len(batch) == 1 for batch in publisher.batches))
        self.assertEqual(
            [batch[0][0] for batch in publisher.batches],
            [
                "homelab-ha-discovery/ppp0/metrics/hpc",
                "homelab-ha-discovery/ppp0/metrics/hpc",
            ],
        )

    def test_docker_timer_publishes_intervals_through_one_publisher(self) -> None:
        samples = [
            self.docker_sample(timestamp=1.0, rx_bytes=1000.0, tx_bytes=2000.0),
            self.docker_sample(timestamp=2.0, rx_bytes=1125.0, tx_bytes=127000.0),
            self.docker_sample(timestamp=3.0, rx_bytes=1250.0, tx_bytes=252000.0),
        ]

        with (
            patch.object(publish_docker_container_metrics, "load_env_files"),
            patch.object(
                publish_docker_container_metrics,
                "MqttPublisher",
                FakePersistentPublisher,
            ),
            patch.object(
                publish_docker_container_metrics,
                "read_docker_container_sample",
                side_effect=samples,
            ),
            patch.object(
                publish_docker_container_metrics.time,
                "sleep",
                side_effect=[None, None, KeyboardInterrupt],
            ),
            patch.object(
                publish_docker_container_metrics,
                "publish_mqtt_many",
            ) as publish_many,
        ):
            result = publish_docker_container_metrics.run_docker_publish_timer(
                60.0,
                "hpc",
                include_label_selectors=(),
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        publish_many.assert_not_called()
        self.assertEqual(len(FakePersistentPublisher.instances), 1)
        publisher = FakePersistentPublisher.instances[0]
        self.assertEqual(
            publisher.default_client_id,
            "homelab-ha-discovery_hpc_docker_metrics",
        )
        self.assertEqual(publisher.enter_count, 1)
        self.assertEqual(publisher.exit_count, 1)
        self.assertEqual(len(publisher.batches), 2)
        self.assertTrue(all(len(batch) == 1 for batch in publisher.batches))
        self.assertEqual(
            [batch[0][0] for batch in publisher.batches],
            [
                "homelab-ha-discovery/hpc/docker/plex/metrics",
                "homelab-ha-discovery/hpc/docker/plex/metrics",
            ],
        )


if __name__ == "__main__":
    unittest.main()
