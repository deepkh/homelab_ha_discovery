from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery import env as env_module


class EnvTest(unittest.TestCase):
    def setUp(self) -> None:
        env_module.ENV_SOURCES.clear()

    def tearDown(self) -> None:
        env_module.ENV_SOURCES.clear()

    def test_load_env_files_skips_when_systemd_already_loaded_env_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "mqtt.env"
            env_file.write_text("HA_MQTT_HOST=file-host\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {env_module.SKIP_ENV_FILES_ENV: "1"},
                clear=True,
            ):
                env_module.load_env_files((str(env_file),))
                self.assertNotIn("HA_MQTT_HOST", os.environ)
                self.assertEqual(env_module.ENV_SOURCES, {})

    def test_load_env_files_reads_file_without_skip_marker(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "mqtt.env"
            env_file.write_text("HA_MQTT_HOST=file-host\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                env_module.load_env_files((str(env_file),))
                self.assertEqual(os.environ["HA_MQTT_HOST"], "file-host")
                self.assertEqual(
                    env_module.ENV_SOURCES["HA_MQTT_HOST"],
                    str(env_file),
                )


if __name__ == "__main__":
    unittest.main()
