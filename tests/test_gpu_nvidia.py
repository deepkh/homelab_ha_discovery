from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.gpu_nvidia import parse_gpu_metrics


class NvidiaGpuMetricsTest(unittest.TestCase):
    def test_parse_nvidia_smi_metrics_with_index(self) -> None:
        self.assertEqual(
            parse_gpu_metrics("2, NVIDIA RTX 4000, 12.34, 512, 1024, 61.4\n"),
            {
                "gpu2": {
                    "GPU Card Name": "NVIDIA RTX 4000",
                    "GPU Usages": 12.3,
                    "Memory Usage": 50.0,
                    "Temperature": 61,
                }
            },
        )

    def test_parse_nvidia_smi_metrics_without_index_for_compatibility(self) -> None:
        self.assertEqual(
            parse_gpu_metrics("NVIDIA RTX 4000, 12.34, 512, 1024, 61.4\n"),
            {
                "gpu0": {
                    "GPU Card Name": "NVIDIA RTX 4000",
                    "GPU Usages": 12.3,
                    "Memory Usage": 50.0,
                    "Temperature": 61,
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
