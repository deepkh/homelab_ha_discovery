from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.network_linux import (
    NetworkCounterSample,
    calculate_network_speed_metrics,
)


class NetworkLinuxTest(unittest.TestCase):
    def test_calculate_network_speed_metrics_uses_mbps(self) -> None:
        self.assertEqual(
            calculate_network_speed_metrics(
                NetworkCounterSample(
                    bytes_recv=1000,
                    bytes_sent=2000,
                    timestamp=1.0,
                ),
                NetworkCounterSample(
                    bytes_recv=1125,
                    bytes_sent=127000,
                    timestamp=2.0,
                ),
            ),
            {
                "Download Speed": 0.001,
                "Upload Speed": 1.0,
            },
        )


if __name__ == "__main__":
    unittest.main()
