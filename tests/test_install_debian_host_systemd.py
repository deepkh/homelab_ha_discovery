from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import call, patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from homelab_ha_discovery.scripts.install_debian_host_systemd import (
    DEFAULT_FRIGATE_METRICS_URL,
    RuntimePaths,
    build_detected_config,
    command_disable,
    command_logs,
    command_restart,
    command_stop,
    command_uninstall,
    render_unit,
    service_command,
    service_unit_name,
)


class InstallDebianHostSystemdTest(unittest.TestCase):
    def make_paths(self, root: Path) -> RuntimePaths:
        return RuntimePaths(
            app_dir=root / "opt" / "homelab-ha-discovery",
            config_dir=root / "etc" / "homelab-ha-discovery",
            systemd_dir=root / "systemd",
            source_root=Path("/checkout"),
        )

    def make_args(self, paths: RuntimePaths, **values: object) -> Namespace:
        args = {
            "app_dir": paths.app_dir,
            "config_dir": paths.config_dir,
            "systemd_dir": paths.systemd_dir,
            "dry_run": False,
        }
        args.update(values)
        return Namespace(**args)

    def write_config(
        self,
        paths: RuntimePaths,
        services: list[dict[str, object]],
    ) -> None:
        paths.config_dir.mkdir(parents=True)
        paths.config_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "ha_device_id": "hpc",
                    "timer_publish_discovery_config": 60.0,
                    "services": services,
                }
            ),
            encoding="utf-8",
        )

    def touch_units(self, paths: RuntimePaths, unit_names: list[str]) -> None:
        paths.systemd_dir.mkdir(parents=True)
        for unit_name in unit_names:
            (paths.systemd_dir / unit_name).write_text("[Service]\n", encoding="utf-8")

    def test_asus_router_connected_clients_unit_name_and_command(self) -> None:
        paths = RuntimePaths(
            app_dir=Path("/opt/homelab-ha-discovery"),
            config_dir=Path("/etc/homelab-ha-discovery"),
            systemd_dir=Path("/etc/systemd/system"),
            source_root=Path("/checkout"),
        )
        service = {
            "type": "asus_router_connected_clients",
            "enabled": True,
            "timer": 1.0,
            "router_name": "ASUS AX86U",
            "ssh_user": "router-user",
            "ssh_ip": "router-ip-address",
            "ssh_port": 22,
            "client_list_command": "cat leases; echo marker; cat clientlist.json",
        }

        self.assertEqual(
            service_unit_name("hpc", service),
            (
                "homelab-ha-discovery-hpc-asus-router-connected-clients-"
                "asus-ax86u.service"
            ),
        )

        command = service_command(paths, "hpc", service, discovery_timer=60.0)
        self.assertEqual(
            command,
            [
                "/opt/homelab-ha-discovery/.venv/bin/python",
                (
                    "/opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/"
                    "publish_asus_router_connected_clients_metrics.py"
                ),
                "--ha-device-id",
                "hpc",
                "--router-name",
                "ASUS AX86U",
                "--ssh-user",
                "router-user",
                "--ssh-ip",
                "router-ip-address",
                "--ssh-port",
                "22",
                "--client-list-command",
                "cat leases; echo marker; cat clientlist.json",
                "--timer",
                "1.0",
                "--timer-publish-discovery-config",
                "60.0",
            ],
        )

    def test_asus_router_network_unit_name_and_command(self) -> None:
        paths = RuntimePaths(
            app_dir=Path("/opt/homelab-ha-discovery"),
            config_dir=Path("/etc/homelab-ha-discovery"),
            systemd_dir=Path("/etc/systemd/system"),
            source_root=Path("/checkout"),
        )
        service = {
            "type": "asus_router_network",
            "enabled": True,
            "timer": 1.0,
            "router_name": "ASUS AX86U",
            "dev": "eth0",
            "ssh_user": "router-user",
            "ssh_ip": "router-ip-address",
            "ssh_port": 22,
            "network_command": "printf network",
        }

        self.assertEqual(
            service_unit_name("hpc", service),
            "homelab-ha-discovery-hpc-asus-router-network-asus-ax86u-eth0.service",
        )

        command = service_command(paths, "hpc", service, discovery_timer=60.0)
        self.assertEqual(
            command,
            [
                "/opt/homelab-ha-discovery/.venv/bin/python",
                (
                    "/opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/"
                    "publish_asus_router_network_metrics.py"
                ),
                "--ha-device-id",
                "hpc",
                "--router-name",
                "ASUS AX86U",
                "--dev",
                "eth0",
                "--ssh-user",
                "router-user",
                "--ssh-ip",
                "router-ip-address",
                "--ssh-port",
                "22",
                "--network-command",
                "printf network",
                "--timer",
                "1.0",
                "--timer-publish-discovery-config",
                "60.0",
            ],
        )

    def test_docker_container_unit_name_and_command(self) -> None:
        paths = RuntimePaths(
            app_dir=Path("/opt/homelab-ha-discovery"),
            config_dir=Path("/etc/homelab-ha-discovery"),
            systemd_dir=Path("/etc/systemd/system"),
            source_root=Path("/checkout"),
        )
        service = {
            "type": "docker_containers",
            "enabled": True,
            "timer": 60.0,
            "include_label": "homelab-ha-discovery.enabled=true",
            "include_labels": ["tier=media"],
            "docker_command": "/usr/bin/docker",
            "expire_after": 0,
            "debug": True,
        }

        self.assertEqual(
            service_unit_name("hpc", service),
            "homelab-ha-discovery-hpc-docker-containers.service",
        )

        command = service_command(paths, "hpc", service, discovery_timer=60.0)
        self.assertEqual(
            command,
            [
                "/opt/homelab-ha-discovery/.venv/bin/python",
                (
                    "/opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/"
                    "publish_docker_container_metrics.py"
                ),
                "--ha-device-id",
                "hpc",
                "--include-label",
                "homelab-ha-discovery.enabled=true",
                "--include-label",
                "tier=media",
                "--docker-command",
                "/usr/bin/docker",
                "--debug",
                "--expire-after",
                "0.0",
                "--timer",
                "60.0",
                "--timer-publish-discovery-config",
                "60.0",
            ],
        )

    def test_frigate_unit_name_and_command(self) -> None:
        paths = RuntimePaths(
            app_dir=Path("/opt/homelab-ha-discovery"),
            config_dir=Path("/etc/homelab-ha-discovery"),
            systemd_dir=Path("/etc/systemd/system"),
            source_root=Path("/checkout"),
        )
        service = {
            "type": "frigate",
            "enabled": True,
            "timer": 10.0,
            "url": "http://127.0.0.1:5000/api/metrics",
            "debug": True,
        }

        self.assertEqual(
            service_unit_name("hpc", service),
            "homelab-ha-discovery-hpc-frigate.service",
        )

        command = service_command(paths, "hpc", service, discovery_timer=60.0)
        self.assertEqual(
            command,
            [
                "/opt/homelab-ha-discovery/.venv/bin/python",
                (
                    "/opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/"
                    "publish_frigate_metrics.py"
                ),
                "--ha-device-id",
                "hpc",
                "--url",
                "http://127.0.0.1:5000/api/metrics",
                "--debug",
                "--timer",
                "10.0",
                "--timer-publish-discovery-config",
                "60.0",
            ],
        )

    def test_expire_after_is_generic_service_option(self) -> None:
        paths = RuntimePaths(
            app_dir=Path("/opt/homelab-ha-discovery"),
            config_dir=Path("/etc/homelab-ha-discovery"),
            systemd_dir=Path("/etc/systemd/system"),
            source_root=Path("/checkout"),
        )
        service = {
            "type": "cpu",
            "enabled": True,
            "timer": 5.0,
            "expire_after": 0,
        }

        command = service_command(paths, "hpc", service, discovery_timer=60.0)
        self.assertEqual(
            command,
            [
                "/opt/homelab-ha-discovery/.venv/bin/python",
                (
                    "/opt/homelab-ha-discovery/src/homelab_ha_discovery/scripts/"
                    "publish_cpu_metrics.py"
                ),
                "--ha-device-id",
                "hpc",
                "--expire-after",
                "0.0",
                "--timer",
                "5.0",
                "--timer-publish-discovery-config",
                "60.0",
            ],
        )

    def test_asus_router_network_unit_names_include_router_and_interface(self) -> None:
        left = {
            "type": "asus_router_network",
            "enabled": True,
            "router_name": "ASUS AX86U",
            "dev": "eth0",
            "ssh_user": "router-user",
            "ssh_ip": "router-ip-address",
        }
        right = {
            "type": "asus_router_network",
            "enabled": True,
            "router_name": "ASUS AX86U",
            "dev": "eth1",
            "ssh_user": "router-user",
            "ssh_ip": "router-ip-address",
        }

        self.assertEqual(
            service_unit_name("hpc", left),
            "homelab-ha-discovery-hpc-asus-router-network-asus-ax86u-eth0.service",
        )
        self.assertEqual(
            service_unit_name("hpc", right),
            "homelab-ha-discovery-hpc-asus-router-network-asus-ax86u-eth1.service",
        )

    def test_detected_config_includes_disabled_asus_router_network_template(
        self,
    ) -> None:
        with (
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_exists",
                return_value=False,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_has_output",
                return_value=False,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_disk_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_nvme_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_network_interfaces",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "http_url_reachable",
                return_value=False,
            ),
        ):
            config = build_detected_config("hpc")

        services = config["services"]
        router_network = [
            service
            for service in services
            if service["type"] == "asus_router_network"
        ]
        self.assertEqual(
            router_network,
            [
                {
                    "type": "asus_router_network",
                    "enabled": False,
                    "timer": 1.0,
                    "expire_after": None,
                    "router_name": "ASUS AX86U",
                    "dev": "eth0",
                    "ssh_user": "<user>",
                    "ssh_ip": "<ip-addr>",
                    "ssh_port": 22,
                    "note": "disabled template; edit SSH settings and enable manually",
                }
            ],
        )

    def test_detected_config_includes_disabled_docker_template(self) -> None:
        def command_exists(command: str) -> bool:
            return command == "docker"

        with (
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_exists",
                side_effect=command_exists,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_has_output",
                return_value=False,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_disk_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_nvme_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_network_interfaces",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "http_url_reachable",
                return_value=False,
            ),
        ):
            config = build_detected_config("hpc")

        services = config["services"]
        docker_entries = [
            service
            for service in services
            if service["type"] == "docker_containers"
        ]
        self.assertEqual(
            docker_entries,
            [
                {
                    "type": "docker_containers",
                    "enabled": False,
                    "timer": 60.0,
                    "expire_after": None,
                    "include_label": "homelab-ha-discovery.enabled=true",
                    "missing_requirements": [],
                    "note": (
                        "disabled template; enable manually after confirming "
                        "Docker socket access"
                    ),
                }
            ],
        )

    def test_detected_config_enables_frigate_when_metrics_are_reachable(self) -> None:
        with (
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_exists",
                return_value=False,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_has_output",
                return_value=False,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_disk_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_nvme_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_network_interfaces",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "http_url_reachable",
                return_value=True,
            ),
        ):
            config = build_detected_config("hpc")

        frigate_entries = [
            service
            for service in config["services"]
            if service["type"] == "frigate"
        ]
        self.assertEqual(
            frigate_entries,
            [
                {
                    "type": "frigate",
                    "enabled": True,
                    "timer": 10.0,
                    "expire_after": None,
                    "url": DEFAULT_FRIGATE_METRICS_URL,
                    "missing_requirements": [],
                }
            ],
        )

    def test_detected_config_adds_disabled_frigate_template_when_unreachable(
        self,
    ) -> None:
        with (
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_exists",
                return_value=False,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "command_has_output",
                return_value=False,
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_disk_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_nvme_devices",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "detect_network_interfaces",
                return_value=[],
            ),
            patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd."
                "http_url_reachable",
                return_value=False,
            ),
        ):
            config = build_detected_config("hpc")

        frigate_entries = [
            service
            for service in config["services"]
            if service["type"] == "frigate"
        ]
        self.assertEqual(
            frigate_entries,
            [
                {
                    "type": "frigate",
                    "enabled": False,
                    "timer": 10.0,
                    "expire_after": None,
                    "url": DEFAULT_FRIGATE_METRICS_URL,
                    "missing_requirements": [],
                    "note": "disabled template; enable after Frigate is running",
                }
            ],
        )

    def test_stop_restart_and_disable_use_configured_units(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = self.make_paths(Path(temp_dir))
            cpu_service = {"type": "cpu", "enabled": True, "timer": 5.0}
            network_service = {
                "type": "network",
                "enabled": True,
                "dev": "ppp0",
                "timer": 1.0,
            }
            self.write_config(paths, [cpu_service, network_service])
            units = [
                service_unit_name("hpc", cpu_service),
                service_unit_name("hpc", network_service),
            ]
            self.touch_units(paths, units)

            with patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd.run_command"
            ) as run_command:
                self.assertEqual(command_stop(self.make_args(paths)), 0)
                run_command.assert_called_once_with(
                    ["systemctl", "stop", *units],
                    False,
                )

                run_command.reset_mock()
                self.assertEqual(command_restart(self.make_args(paths)), 0)
                run_command.assert_has_calls(
                    [
                        call(["systemctl", "daemon-reload"], False),
                        call(["systemctl", "restart", *units], False),
                    ]
                )

                run_command.reset_mock()
                self.assertEqual(
                    command_disable(self.make_args(paths, now=True)),
                    0,
                )
                run_command.assert_called_once_with(
                    ["systemctl", "disable", "--now", *units],
                    False,
                )

    def test_uninstall_scans_generated_unit_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = self.make_paths(Path(temp_dir))
            generated_units = [
                "homelab-ha-discovery-hpc-cpu.service",
                "homelab-ha-discovery-hpc-network-ppp0.service",
            ]
            self.touch_units(paths, generated_units + ["other.service"])

            with patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd.run_command"
            ) as run_command:
                self.assertEqual(command_uninstall(self.make_args(paths)), 0)

            run_command.assert_has_calls(
                [
                    call(["systemctl", "stop", *generated_units], False),
                    call(["systemctl", "disable", *generated_units], False),
                    call(["systemctl", "daemon-reload"], False),
                ]
            )
            for unit_name in generated_units:
                self.assertFalse((paths.systemd_dir / unit_name).exists())
            self.assertTrue((paths.systemd_dir / "other.service").exists())

    def test_logs_command_builds_journalctl_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            paths = self.make_paths(Path(temp_dir))
            cpu_service = {"type": "cpu", "enabled": True, "timer": 5.0}
            self.write_config(paths, [cpu_service])
            unit_name = service_unit_name("hpc", cpu_service)

            with patch(
                "homelab_ha_discovery.scripts.install_debian_host_systemd.run_command"
            ) as run_command:
                self.assertEqual(
                    command_logs(
                        self.make_args(
                            paths,
                            follow=True,
                            lines=200,
                            since="1 hour ago",
                        )
                    ),
                    0,
                )

            run_command.assert_called_once_with(
                [
                    "journalctl",
                    "-f",
                    "-n",
                    "200",
                    "--since",
                    "1 hour ago",
                    "-u",
                    unit_name,
                ],
                False,
            )

    def test_rendered_unit_restarts_after_sixty_seconds(self) -> None:
        paths = RuntimePaths(
            app_dir=Path("/opt/homelab-ha-discovery"),
            config_dir=Path("/etc/homelab-ha-discovery"),
            systemd_dir=Path("/etc/systemd/system"),
            source_root=Path("/checkout"),
        )
        unit = render_unit(
            paths,
            "hpc",
            {"type": "cpu", "enabled": True, "timer": 5.0},
            discovery_timer=60.0,
        )

        self.assertIn("Restart=always\nRestartSec=60s\n", unit.content)


if __name__ == "__main__":
    unittest.main()
