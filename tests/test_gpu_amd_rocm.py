from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.gpu_amd_rocm import parse_gpu_metrics


class AmdRocmGpuMetricsTest(unittest.TestCase):
    def test_parse_rocm_smi_json_metrics(self) -> None:
        output = json.dumps(
            {
                "card1": {
                    "Device Name": "AMD Radeon RX 7900 XTX",
                    "GPU use (%)": "100.0",
                    "GPU Memory Allocated (VRAM%)": "0.04",
                    "Temperature (Sensor edge) (C)": "72.6",
                },
                "card0": {
                    "Card Series": "AMD Instinct MI210",
                    "GPU use (%)": "12.34%",
                    "GPU Memory Allocated (VRAM%)": "45.67%",
                    "Temperature (Sensor edge) (C)": "61.4c",
                },
            }
        )

        self.assertEqual(
            parse_gpu_metrics(output),
            {
                "gpu0": {
                    "GPU Card Name": "AMD Instinct MI210",
                    "GPU Usages": 12.3,
                    "Memory Usage": 45.7,
                    "Temperature": 61,
                },
                "gpu1": {
                    "GPU Card Name": "AMD Radeon RX 7900 XTX",
                    "GPU Usages": 100.0,
                    "Memory Usage": 0.0,
                    "Temperature": 73,
                },
            },
        )

    def test_parse_rocm_smi_rejects_empty_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "Could not find AMD ROCm GPU"):
            parse_gpu_metrics("{}")

    def test_parse_rocm_smi_rejects_missing_metric(self) -> None:
        output = json.dumps(
            {
                "card0": {
                    "Device Name": "AMD Instinct MI210",
                    "GPU use (%)": "12",
                    "Temperature (Sensor edge) (C)": "61",
                }
            }
        )

        with self.assertRaisesRegex(ValueError, "memory usage"):
            parse_gpu_metrics(output)

    def test_parse_rocm_smi_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unexpected rocm-smi JSON output"):
            parse_gpu_metrics("not json")


if __name__ == "__main__":
    unittest.main()
