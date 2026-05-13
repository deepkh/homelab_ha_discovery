from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.podman_containers import (
    PodmanContainerSample,
    PodmanContainerStats,
    calculate_podman_container_metrics,
    parse_byte_quantity,
    parse_label_selector,
    parse_pair,
    parse_podman_inspect,
    parse_podman_stats,
)


class PodmanContainersTest(unittest.TestCase):
    def test_parse_label_selector_supports_key_and_key_value(self) -> None:
        self.assertEqual(
            parse_label_selector("homelab-ha-discovery.enabled=true"),
            ("homelab-ha-discovery.enabled", "true"),
        )
        self.assertEqual(
            parse_label_selector("homelab-ha-discovery.enabled"),
            ("homelab-ha-discovery.enabled", "true"),
        )
        self.assertEqual(parse_label_selector("tier"), ("tier", None))

    def test_parse_label_selector_rejects_enabled_false(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be true"):
            parse_label_selector("homelab-ha-discovery.enabled=false")

    def test_parse_byte_quantity_supports_podman_units_and_spaces(self) -> None:
        self.assertEqual(parse_byte_quantity("1kB"), 1000.0)
        self.assertEqual(parse_byte_quantity("1 KiB"), 1024.0)
        self.assertEqual(parse_byte_quantity("2.5 MB"), 2_500_000.0)

    def test_parse_pair_treats_unavailable_rootless_network_as_zero(self) -> None:
        self.assertEqual(parse_pair("-- / --", "netio"), (0.0, 0.0))

    def test_parse_inspect_filters_labels_and_uses_component_override(self) -> None:
        inspect_output = json.dumps(
            [
                {
                    "Id": "abc123def456789",
                    "Name": "plex",
                    "Config": {
                        "Labels": {
                            "homelab-ha-discovery.enabled": "true",
                            "homelab-ha-discovery.component": "Media Plex",
                        }
                    },
                    "State": {
                        "Status": "running",
                        "Healthcheck": {"Status": "healthy"},
                    },
                    "RestartCount": 2,
                },
                {
                    "Id": "def456abc123789",
                    "Name": "gitlab",
                    "Config": {"Labels": {}},
                    "State": {"Status": "running"},
                    "RestartCount": 0,
                },
            ]
        )

        containers = parse_podman_inspect(
            inspect_output,
            include_label_selectors=(
                ("homelab-ha-discovery.enabled", "true"),
            ),
        )

        self.assertEqual(list(containers), ["abc123def456789"])
        container = containers["abc123def456789"]
        self.assertEqual(container.name, "plex")
        self.assertEqual(container.component, "media_plex")
        self.assertEqual(container.state, "running")
        self.assertEqual(container.health, "healthy")
        self.assertEqual(container.restart_count, 2)

    def test_parse_inspect_rejects_duplicate_components(self) -> None:
        inspect_output = json.dumps(
            [
                {
                    "Id": "abc123def456789",
                    "Name": "plex",
                    "Config": {"Labels": {}},
                    "State": {"Status": "running"},
                    "RestartCount": 0,
                },
                {
                    "Id": "def456abc123789",
                    "Name": "Plex",
                    "Config": {"Labels": {}},
                    "State": {"Status": "running"},
                    "RestartCount": 0,
                },
            ]
        )

        with self.assertRaisesRegex(ValueError, "multiple Podman containers"):
            parse_podman_inspect(inspect_output)

    def test_parse_stats_matches_truncated_container_id(self) -> None:
        containers = parse_podman_inspect(
            json.dumps(
                [
                    {
                        "Id": "abc123def456789",
                        "Name": "plex",
                        "Config": {"Labels": {}},
                        "State": {"Status": "running"},
                        "RestartCount": 0,
                    }
                ]
            )
        )
        stats = parse_podman_stats(
            json.dumps(
                [
                    {
                        "id": "abc123def456",
                        "name": "plex",
                        "cpu_percent": "2.318%",
                        "mem_usage": "512 MiB / 8 GiB",
                        "mem_percent": "6.25%",
                        "netio": "1kB / 2kB",
                    }
                ]
            ),
            containers,
        )

        self.assertIn("abc123def456789", stats)
        self.assertEqual(stats["abc123def456789"].cpu_usage_percent, 2.318)
        self.assertEqual(stats["abc123def456789"].network_rx_bytes, 1000.0)
        self.assertEqual(stats["abc123def456789"].network_tx_bytes, 2000.0)

    def test_parse_stats_allows_unavailable_cpu_and_network_values(self) -> None:
        containers = parse_podman_inspect(
            json.dumps(
                [
                    {
                        "Id": "abc123def456789",
                        "Name": "plex",
                        "Config": {"Labels": {}},
                        "State": {"Status": "running"},
                        "RestartCount": 0,
                    }
                ]
            )
        )
        stats = parse_podman_stats(
            json.dumps(
                [
                    {
                        "id": "abc123def456",
                        "name": "plex",
                        "cpu_percent": "--",
                        "mem_usage": "-- / --",
                        "mem_percent": "--",
                        "netio": "-- / --",
                    }
                ]
            ),
            containers,
        )

        self.assertEqual(stats["abc123def456789"].cpu_usage_percent, 0.0)
        self.assertEqual(stats["abc123def456789"].memory_limit_bytes, 0.0)
        self.assertEqual(stats["abc123def456789"].network_rx_bytes, 0.0)

    def test_calculate_podman_container_metrics_uses_mbps(self) -> None:
        containers = parse_podman_inspect(
            json.dumps(
                [
                    {
                        "Id": "abc123def456789",
                        "Name": "plex",
                        "Config": {"Labels": {}},
                        "State": {
                            "Status": "running",
                            "Healthcheck": {"Status": "healthy"},
                        },
                        "RestartCount": 2,
                    }
                ]
            )
        )
        previous = PodmanContainerSample(
            containers=containers,
            stats={
                "abc123def456789": PodmanContainerStats(
                    cpu_usage_percent=1.0,
                    memory_usage_bytes=1_000_000.0,
                    memory_limit_bytes=10_000_000.0,
                    memory_usage_percent=10.0,
                    network_rx_bytes=1000.0,
                    network_tx_bytes=2000.0,
                )
            },
            timestamp=1.0,
        )
        current = PodmanContainerSample(
            containers=containers,
            stats={
                "abc123def456789": PodmanContainerStats(
                    cpu_usage_percent=2.318,
                    memory_usage_bytes=512_400_000.0,
                    memory_limit_bytes=8_192_000_000.0,
                    memory_usage_percent=6.25,
                    network_rx_bytes=1125.0,
                    network_tx_bytes=127000.0,
                )
            },
            timestamp=2.0,
        )

        metrics, skipped_components = calculate_podman_container_metrics(
            previous,
            current,
        )

        self.assertEqual(skipped_components, [])
        self.assertEqual(len(metrics), 1)
        self.assertEqual(
            metrics[0].payload,
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


if __name__ == "__main__":
    unittest.main()
