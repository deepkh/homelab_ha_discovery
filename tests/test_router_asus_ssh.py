from __future__ import annotations

from pathlib import Path
import sys
import unittest


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.collectors.router_asus_ssh import (
    asus_router_connected_clients_debug_lines,
    parse_asus_router_connected_clients,
    parse_asus_router_network_metrics,
)


AX86U_PRO_COMBINED_OUTPUT = """
1710000000 02:00:00:00:00:01 192.0.2.72 client_2g_01 *
1710000001 02:00:00:00:00:02 192.0.2.73 client_5g_01 *
1710000002 02:00:00:00:00:03 192.0.2.10 client_wired_01 *
1710000003 02:00:00:00:00:04 192.0.2.11 client_wired_02 *
1710000004 02:00:00:00:00:05 192.0.2.99 dhcp_only_client *
---END_LEASES---
{
  "maclist": ["02:00:00:00:00:05"],
  "2G": [
    {"mac": "02:00:00:00:00:01", "ip": "192.0.2.72", "rssi": "-68"}
  ],
  "5G": {
    "02:00:00:00:00:02": {"ip": "192.0.2.73", "rssi": -42}
  },
  "wired_mac": [
    "02:00:00:00:00:03",
    "02:00:00:00:00:04"
  ]
}
"""


AX86U_COMBINED_OUTPUT = """
1710000000 02:00:00:00:00:06 192.0.2.80 fallback_lease_client *
1710000001 02:00:00:00:00:07 192.0.2.81 * *
---END_LEASES---
{
  "2G": [
    ["02:00:00:00:00:01", "192.0.2.72", "-68"],
    ["02:00:00:00:00:02", "192.0.2.73"]
  ],
  "5G-1": [
    {"client_mac": "02:00:00:00:00:08", "ip_addr": "192.0.2.80", "signal": "-55"}
  ],
  "wired_mac": {
    "02:00:00:00:00:07": {"ip": "192.0.2.81", "isWL": "0"}
  }
}
"""


AX86U_WRAPPED_COMBINED_OUTPUT = """
1710000000 02:00:00:00:00:09 192.0.2.107 sample_laptop 01:02:00:00:00:00:09
1710000001 02:00:00:00:00:10 192.0.2.11 sample_phone 01:02:00:00:00:00:10
1710000002 02:00:00:00:00:11 192.0.2.21 sample_linux_host 01:02:00:00:00:00:11
1710000003 02:00:00:00:00:12 192.0.2.61 sample_sensor_01 01:02:00:00:00:00:12
1710000004 02:00:00:00:00:13 192.0.2.71 sample_switch_01 01:02:00:00:00:00:13
1710000005 02:00:00:00:00:01 192.0.2.72 client_2g_01 01:02:00:00:00:00:01
1710000006 02:00:00:00:00:14 192.0.2.62 sample_sensor_02 01:02:00:00:00:00:14
---END_LEASES---
{"02:00:00:00:00:20":{"2G":{"02:00:00:00:00:21":{"ip":"192.0.2.41","rssi":"-35"},"02:00:00:00:00:01":{"ip":"192.0.2.72","rssi":"-68"},"02:00:00:00:00:13":{"ip":"192.0.2.71","rssi":"-59"},"02:00:00:00:00:12":{"ip":"192.0.2.61","rssi":"-30"},"02:00:00:00:00:11":{"ip":"192.0.2.21","rssi":"-42"}},"5G":{"02:00:00:00:00:10":{"ip":"192.0.2.11","rssi":"-49"}},"wired_mac":{"02:00:00:00:00:26":{"ip":"192.0.2.27"},"02:00:00:00:00:27":{"ip":"192.0.2.3"}}}}
"""


class AsusRouterConnectedClientsParserTest(unittest.TestCase):
    def test_parse_connected_clients_from_ax86u_pro_sample(self) -> None:
        self.assertEqual(
            parse_asus_router_connected_clients(AX86U_PRO_COMBINED_OUTPUT),
            [
                {
                    "mac": "02:00:00:00:00:01",
                    "ip": "192.0.2.72",
                    "rssi": "-68",
                    "interface": "2G",
                    "name": "client_2g_01",
                },
                {
                    "mac": "02:00:00:00:00:02",
                    "ip": "192.0.2.73",
                    "rssi": "-42",
                    "interface": "5G",
                    "name": "client_5g_01",
                },
                {
                    "mac": "02:00:00:00:00:03",
                    "ip": "192.0.2.10",
                    "rssi": "N/A",
                    "interface": "wired_mac",
                    "name": "client_wired_01",
                },
                {
                    "mac": "02:00:00:00:00:04",
                    "ip": "192.0.2.11",
                    "rssi": "N/A",
                    "interface": "wired_mac",
                    "name": "client_wired_02",
                },
            ],
        )

    def test_parse_connected_clients_from_ax86u_sample(self) -> None:
        self.assertEqual(
            parse_asus_router_connected_clients(AX86U_COMBINED_OUTPUT),
            [
                {
                    "mac": "02:00:00:00:00:01",
                    "ip": "192.0.2.72",
                    "rssi": "-68",
                    "interface": "2G",
                    "name": " - ",
                },
                {
                    "mac": "02:00:00:00:00:02",
                    "ip": "192.0.2.73",
                    "rssi": "N/A",
                    "interface": "2G",
                    "name": " - ",
                },
                {
                    "mac": "02:00:00:00:00:08",
                    "ip": "192.0.2.80",
                    "rssi": "-55",
                    "interface": "5G-1",
                    "name": "fallback_lease_client",
                },
                {
                    "mac": "02:00:00:00:00:07",
                    "ip": "192.0.2.81",
                    "rssi": "N/A",
                    "interface": "wired_mac",
                    "name": " - ",
                },
            ],
        )

    def test_debug_lines_show_parser_shape(self) -> None:
        debug_lines = asus_router_connected_clients_debug_lines(
            AX86U_PRO_COMBINED_OUTPUT
        )
        joined_debug = "\n".join(debug_lines)

        self.assertIn("dnsmasq leases: nonempty_lines=5", joined_debug)
        self.assertIn("clientlist top-level keys (4)", joined_debug)
        self.assertIn("top-level key 'wired_mac'", joined_debug)
        self.assertIn("extracted_clients=2", joined_debug)

    def test_parse_connected_clients_from_wrapped_ax86u_sample(self) -> None:
        self.assertEqual(
            parse_asus_router_connected_clients(AX86U_WRAPPED_COMBINED_OUTPUT),
            [
                {
                    "mac": "02:00:00:00:00:21",
                    "ip": "192.0.2.41",
                    "rssi": "-35",
                    "interface": "2G",
                    "name": " - ",
                },
                {
                    "mac": "02:00:00:00:00:01",
                    "ip": "192.0.2.72",
                    "rssi": "-68",
                    "interface": "2G",
                    "name": "client_2g_01",
                },
                {
                    "mac": "02:00:00:00:00:13",
                    "ip": "192.0.2.71",
                    "rssi": "-59",
                    "interface": "2G",
                    "name": "sample_switch_01",
                },
                {
                    "mac": "02:00:00:00:00:12",
                    "ip": "192.0.2.61",
                    "rssi": "-30",
                    "interface": "2G",
                    "name": "sample_sensor_01",
                },
                {
                    "mac": "02:00:00:00:00:11",
                    "ip": "192.0.2.21",
                    "rssi": "-42",
                    "interface": "2G",
                    "name": "sample_linux_host",
                },
                {
                    "mac": "02:00:00:00:00:10",
                    "ip": "192.0.2.11",
                    "rssi": "-49",
                    "interface": "5G",
                    "name": "sample_phone",
                },
                {
                    "mac": "02:00:00:00:00:26",
                    "ip": "192.0.2.27",
                    "rssi": "N/A",
                    "interface": "wired_mac",
                    "name": " - ",
                },
                {
                    "mac": "02:00:00:00:00:27",
                    "ip": "192.0.2.3",
                    "rssi": "N/A",
                    "interface": "wired_mac",
                    "name": " - ",
                },
            ],
        )


class AsusRouterNetworkParserTest(unittest.TestCase):
    def test_parse_network_samples_as_mbps(self) -> None:
        self.assertEqual(
            parse_asus_router_network_metrics(
                "sample1 1000 2000\n"
                "sample2 1125 127000\n"
                "download_mbps 0.001000\n"
                "upload_mbps 1.000000\n"
            ),
            {
                "Download Speed": 0.001,
                "Upload Speed": 1.0,
            },
        )

    def test_parse_network_metrics_output(self) -> None:
        self.assertEqual(
            parse_asus_router_network_metrics(
                "download_mbps 0.001000\nupload_mbps 1.000000\n"
            ),
            {
                "Download Speed": 0.001,
                "Upload Speed": 1.0,
            },
        )

    def test_missing_network_interface_output_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing speed metrics"):
            parse_asus_router_network_metrics("")

    def test_decreased_network_counters_fail(self) -> None:
        with self.assertRaisesRegex(ValueError, "counters decreased"):
            parse_asus_router_network_metrics("sample1 1000 2000\nsample2 999 2001\n")

    def test_malformed_network_output_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "Could not parse"):
            parse_asus_router_network_metrics("not network data\n")


if __name__ == "__main__":
    unittest.main()
