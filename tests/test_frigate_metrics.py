from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.frigate_metrics import parse_frigate_metrics


FRIGATE_SAMPLE = """
# HELP frigate_cpu_usage_percent Process CPU usage percentage
# TYPE frigate_cpu_usage_percent gauge
frigate_cpu_usage_percent{pid="ffmpeg.front_door",name="ffmpeg",process="ffmpeg",type="process",cmdline="ffmpeg"} 99.9
frigate_cpu_usage_percent{pid="frigate.full_system",name="frigate",process="frigate",type="process",cmdline="python"} 12.3456
# HELP frigate_mem_usage_percent Process memory usage percentage
# TYPE frigate_mem_usage_percent gauge
frigate_mem_usage_percent{pid="frigate.full_system",name="frigate",process="frigate",type="process",cmdline="python"} 45.6789
frigate_mem_usage_percent{pid="ffmpeg.front_door",name="ffmpeg",process="ffmpeg",type="process",cmdline="ffmpeg"} 88.8
# HELP frigate_camera_fps Frames per second being consumed from your camera
# TYPE frigate_camera_fps gauge
frigate_camera_fps{camera_name="front_door"} 5.0
frigate_camera_fps{camera_name="garage"} 6.1259
frigate_process_fps{camera_name="front_door"} 4.5
frigate_process_fps{camera_name="garage"} 5.5
frigate_skipped_fps{camera_name="front_door"} 0
frigate_skipped_fps{camera_name="garage"} 0.25
frigate_detection_fps{camera_name="front_door"} 3.25
frigate_detection_fps{camera_name="garage"} 2.75
# HELP frigate_detector_inference_speed_seconds Time spent running object detection in seconds
# TYPE frigate_detector_inference_speed_seconds gauge
frigate_detector_inference_speed_seconds{name="coral"} 0.0112
frigate_detector_inference_speed_seconds{name="cpu"} 0.0987
# HELP frigate_gpu_usage_percent GPU utilization percentage
# TYPE frigate_gpu_usage_percent gauge
frigate_gpu_usage_percent{gpu_name="intel-vaapi"} 22.2222
frigate_gpu_usage_percent{gpu_name="nvidia 0"} 33.3333
frigate_gpu_mem_usage_percent{gpu_name="intel-vaapi"} 44.4444
frigate_gpu_mem_usage_percent{gpu_name="nvidia 0"} 55.5555
# HELP frigate_storage_free_bytes Storage free bytes
# TYPE frigate_storage_free_bytes gauge
frigate_storage_free_bytes{storage="/media/frigate/recordings"} 1234567890
frigate_storage_free_bytes{storage="/tmp/cache"} 2000000000
frigate_storage_used_bytes{storage="/media/frigate/recordings"} 9876543210
frigate_storage_used_bytes{storage="/tmp/cache"} 3000000000
"""


class FrigateMetricsTest(unittest.TestCase):
    def test_parse_frigate_metrics_groups_dynamic_labels(self) -> None:
        metrics = parse_frigate_metrics(FRIGATE_SAMPLE)

        self.assertEqual(
            metrics,
            {
                "system": {
                    "CPU Usage": 12.346,
                    "Memory Usage": 45.679,
                },
                "cameras": {
                    "front_door": {
                        "Camera FPS": 5.0,
                        "Process FPS": 4.5,
                        "Skipped FPS": 0.0,
                        "Detection FPS": 3.25,
                    },
                    "garage": {
                        "Camera FPS": 6.126,
                        "Process FPS": 5.5,
                        "Skipped FPS": 0.25,
                        "Detection FPS": 2.75,
                    },
                },
                "detectors": {
                    "coral": {
                        "Inference Speed": 0.011,
                    },
                    "cpu": {
                        "Inference Speed": 0.099,
                    },
                },
                "gpus": {
                    "intel-vaapi": {
                        "GPU Usage": 22.222,
                        "Memory Usage": 44.444,
                    },
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
                    "/tmp/cache": {
                        "Free GB": 2.0,
                        "Used GB": 3.0,
                    },
                },
            },
        )

    def test_missing_required_metric_family_fails(self) -> None:
        incomplete = "\n".join(
            line
            for line in FRIGATE_SAMPLE.splitlines()
            if not line.startswith("frigate_storage_used_bytes")
        )

        with self.assertRaisesRegex(
            ValueError,
            "missing Frigate metric family: frigate_storage_used_bytes",
        ):
            parse_frigate_metrics(incomplete)

    def test_missing_full_system_pid_fails(self) -> None:
        incomplete = FRIGATE_SAMPLE.replace(
            'pid="frigate.full_system"',
            'pid="frigate.other"',
        )

        with self.assertRaisesRegex(
            ValueError,
            "pid='frigate.full_system'",
        ):
            parse_frigate_metrics(incomplete)

    def test_malformed_prometheus_line_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid Prometheus metric line"):
            parse_frigate_metrics(FRIGATE_SAMPLE + "\nnot a metric\n")


if __name__ == "__main__":
    unittest.main()
