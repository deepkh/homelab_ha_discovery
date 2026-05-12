from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
import math
from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.discovery import (
    MetricIdentity,
    effective_expire_after,
    sensor_discovery_config,
    validate_expire_after_seconds,
)


class DiscoveryExpireAfterTest(unittest.TestCase):
    def test_validate_expire_after_rejects_negative_and_nan(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertFalse(validate_expire_after_seconds(-1.0))
            self.assertFalse(validate_expire_after_seconds(math.nan))

        self.assertIn("--expire-after", stderr.getvalue())

    def test_validate_expire_after_accepts_zero_and_positive_values(self) -> None:
        self.assertTrue(validate_expire_after_seconds(None))
        self.assertTrue(validate_expire_after_seconds(0.0))
        self.assertTrue(validate_expire_after_seconds(30.0))

    def test_effective_expire_after_uses_timer_default(self) -> None:
        self.assertEqual(effective_expire_after(None, 60.0), 180.0)
        self.assertIsNone(effective_expire_after(None, None))
        self.assertIsNone(effective_expire_after(0.0, 60.0))
        self.assertEqual(effective_expire_after(30.0, 60.0), 30.0)

    def test_sensor_discovery_config_serializes_expire_after_when_effective(
        self,
    ) -> None:
        identity = MetricIdentity(
            host="hpc",
            component="cpu",
            metric="usage",
            state_topic_override="state/topic",
        )

        config = sensor_discovery_config(
            identity,
            name="hpc CPU Usage",
            value_template="{{ value_json['CPU Usages'] }}",
            expire_after=60.2,
        )

        self.assertEqual(config["expire_after"], 61)
        self.assertEqual(json.loads(json.dumps(config))["expire_after"], 61)

    def test_sensor_discovery_config_omits_expire_after_when_disabled(self) -> None:
        identity = MetricIdentity(
            host="hpc",
            component="cpu",
            metric="usage",
            state_topic_override="state/topic",
        )

        self.assertNotIn(
            "expire_after",
            sensor_discovery_config(identity, name="hpc CPU Usage"),
        )
        self.assertNotIn(
            "expire_after",
            sensor_discovery_config(
                identity,
                name="hpc CPU Usage",
                expire_after=0.0,
            ),
        )


if __name__ == "__main__":
    unittest.main()
