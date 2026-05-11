from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.scripts import publish_asus_router_network_metrics as script


class PublishAsusRouterNetworkMetricsTest(unittest.TestCase):
    def test_discovery_topics_include_router_and_interface(self) -> None:
        state_topic = script.asus_router_network_metrics_state_topic(
            "hpc",
            "asus_ax86u",
            "eth0",
        )

        with patch.object(script, "publish_mqtt") as publish_mqtt:
            script.publish_asus_router_network_discovery(
                "hpc",
                "ASUS AX86U",
                "asus_ax86u",
                "eth0",
                state_topic,
            )

        self.assertEqual(
            [call.args[0] for call in publish_mqtt.call_args_list],
            [
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_asus_ax86u_eth0_download_speed/config"
                ),
                (
                    "homeassistant/sensor/"
                    "homelab_ha_discovery_hpc_asus_ax86u_eth0_upload_speed/config"
                ),
            ],
        )
        payloads = [
            json.loads(call.args[1])
            for call in publish_mqtt.call_args_list
        ]
        self.assertEqual(payloads[0]["name"], "hpc ASUS AX86U eth0 Download Speed")
        self.assertEqual(payloads[0]["unit_of_measurement"], "Mbps")
        self.assertEqual(payloads[0]["state_topic"], state_topic)
        self.assertEqual(
            payloads[0]["value_template"],
            "{{ value_json['Download Speed'] }}",
        )
        self.assertTrue(
            all(call.kwargs["retain"] for call in publish_mqtt.call_args_list)
        )

    def test_publish_state_payload_uses_mbps_values(self) -> None:
        with (
            patch.object(script, "load_env_files"),
            patch.object(
                script,
                "run_asus_router_network",
                return_value="sample1 1000 2000\nsample2 1125 127000\n",
            ) as run_network,
            patch.object(script, "publish_mqtt") as publish_mqtt,
            patch.dict(script.os.environ, {}, clear=True),
        ):
            result = script.publish_asus_router_network_metrics(
                (),
                "hpc",
                "ASUS AX86U",
                "eth0",
                "router-user",
                "router-ip-address",
                ssh_port=22,
                publisher_only=True,
            )

        self.assertEqual(result, 0)
        run_network.assert_called_once_with(
            "router-user",
            "router-ip-address",
            "eth0",
            ssh_port=22,
            network_command=None,
        )
        publish_mqtt.assert_called_once()
        self.assertEqual(
            publish_mqtt.call_args.args[0],
            "homelab-ha-discovery/asus_ax86u/eth0/metrics/hpc",
        )
        self.assertEqual(
            json.loads(publish_mqtt.call_args.args[1]),
            {
                "Download Speed": 0.001,
                "Upload Speed": 1.0,
            },
        )
        self.assertEqual(
            publish_mqtt.call_args.kwargs["default_client_id"],
            "homelab-ha-discovery_hpc_asus_ax86u_eth0_network_metrics",
        )


if __name__ == "__main__":
    unittest.main()
