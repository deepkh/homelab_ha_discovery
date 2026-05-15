from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.gpu_intel_qsv import parse_gpu_metrics


class IntelQsvGpuMetricsTest(unittest.TestCase):
    def test_parse_intel_gpu_top_json_metrics(self) -> None:
        output = json.dumps(
            [
                {
                    "engines": {
                        "Render/3D/0": {"busy": "3.24"},
                        "Blitter/0": {"busy": 0.01},
                        "Video/0": {"busy": 18.44},
                        "Video/1": {"busy": 12.3},
                        "VideoEnhance/0": {"busy": "4.49%"},
                        "Compute/0": {"busy": "-"},
                    }
                }
            ]
        )

        self.assertEqual(
            parse_gpu_metrics(output),
            {
                "gpu0": {
                    "GPU Card Name": "Intel GPU",
                    "GPU Usages": 18.4,
                    "Memory Usage": None,
                    "Temperature": None,
                    "QSV Available": True,
                    "QSV Active": True,
                    "Render/3D Busy": 3.2,
                    "Blitter Busy": 0.0,
                    "Video Busy": 18.4,
                    "VideoEnhance Busy": 4.5,
                    "Compute Busy": None,
                }
            },
        )

    def test_parse_timeout_truncated_json_array(self) -> None:
        complete_sample = json.dumps({"engines": {"Video/0": {"busy": 2.2}}})
        output = f"[{complete_sample}, {{\"engines\": {{\"Video/0\""

        self.assertEqual(parse_gpu_metrics(output)["gpu0"]["Video Busy"], 2.2)

    def test_parse_rejects_empty_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "Could not find Intel QSV GPU"):
            parse_gpu_metrics("")

    def test_parse_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unexpected intel_gpu_top JSON"):
            parse_gpu_metrics("not json")

    def test_missing_busy_values_are_none(self) -> None:
        output = json.dumps(
            [
                {
                    "engines": {
                        "Video/0": {"busy": "-"},
                        "VideoEnhance/0": {},
                    }
                }
            ]
        )

        metrics = parse_gpu_metrics(output)["gpu0"]

        self.assertIsNone(metrics["Video Busy"])
        self.assertIsNone(metrics["VideoEnhance Busy"])
        self.assertIsNone(metrics["GPU Usages"])
        self.assertTrue(metrics["QSV Available"])
        self.assertFalse(metrics["QSV Active"])

    def test_video_engines_aggregate_by_max_busy(self) -> None:
        output = json.dumps(
            [
                {
                    "engines": {
                        "Video/0": {"busy": 10.0},
                        "Video/1": {"busy": 25.5},
                    }
                }
            ]
        )

        self.assertEqual(parse_gpu_metrics(output)["gpu0"]["Video Busy"], 25.5)

    def test_qsv_active_false_when_only_render_is_busy(self) -> None:
        output = json.dumps(
            [
                {
                    "engines": {
                        "Render/3D/0": {"busy": 42.0},
                    }
                }
            ]
        )

        metrics = parse_gpu_metrics(output)["gpu0"]

        self.assertEqual(metrics["GPU Usages"], 42.0)
        self.assertFalse(metrics["QSV Active"])


if __name__ == "__main__":
    unittest.main()
