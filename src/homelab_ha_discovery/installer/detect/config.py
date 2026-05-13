"""Detected host metrics config builder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homelab_ha_discovery.installer.config_io import (
    DEFAULT_CONTAINER_INCLUDE_LABEL,
    DEFAULT_FRIGATE_METRICS_URL,
    DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG,
    SCHEMA_VERSION,
    service_entry,
)
from homelab_ha_discovery.installer.detect.commands import command_exists
from homelab_ha_discovery.installer.detect.frigate import http_url_reachable
from homelab_ha_discovery.installer.detect.gpu import (
    detect_amd_rocm_gpu_indexes,
    detect_nvidia_gpu_indexes,
)
from homelab_ha_discovery.installer.detect.network import detect_network_interfaces
from homelab_ha_discovery.installer.detect.podman import (
    detected_podman_service_entries,
)
from homelab_ha_discovery.installer.detect.storage import (
    detect_disk_devices,
    detect_nvme_devices,
)


GENERATED_BY = "install_debian_host_systemd.py"

def build_detected_config(
    device: str,
    rootless_podman_users: list[str] | tuple[str, ...] = (),
    include_podman: bool = True,
    podman_socket: str | None = None,
    rootless_podman_uids: list[int] | tuple[int, ...] = (),
    auto_discover_rootless_podman: bool = False,
) -> dict[str, Any]:
    services: list[dict[str, Any]] = []

    cpu_missing = [
        command
        for command in ("top", "sensors")
        if not command_exists(command)
    ]
    services.append(
        service_entry(
            "cpu",
            not cpu_missing,
            missing_requirements=cpu_missing,
        )
    )

    nvidia_exists = command_exists("nvidia-smi")
    nvidia_indexes = detect_nvidia_gpu_indexes() if nvidia_exists else []
    nvidia_values: dict[str, Any] = {
        "collector": "nvidia",
        "missing_requirements": [] if nvidia_exists else ["nvidia-smi"],
        "note": (
            "publishes selected NVIDIA GPUs in one timer loop"
            if nvidia_indexes
            else "disabled template; enable after NVIDIA tooling detects GPUs"
        ),
    }
    if nvidia_indexes:
        nvidia_values["gpu_indexes"] = nvidia_indexes
    services.append(
        service_entry(
            "gpu",
            bool(nvidia_indexes),
            **nvidia_values,
        )
    )

    amd_rocm_exists = command_exists("rocm-smi")
    amd_rocm_indexes = detect_amd_rocm_gpu_indexes() if amd_rocm_exists else []
    if amd_rocm_exists:
        amd_rocm_values: dict[str, Any] = {
            "collector": "amd_rocm",
            "missing_requirements": [],
            "note": (
                "publishes selected AMD ROCm GPUs in one timer loop"
                if amd_rocm_indexes
                else "disabled template; enable after rocm-smi detects GPUs"
            ),
        }
        if amd_rocm_indexes:
            amd_rocm_values["gpu_indexes"] = amd_rocm_indexes
        services.append(
            service_entry(
                "gpu",
                bool(amd_rocm_indexes),
                **amd_rocm_values,
            )
        )

    smart_missing = [
        command
        for command in ("sudo", "smartctl")
        if not command_exists(command)
    ]
    smart_enabled = not smart_missing
    for dev in detect_disk_devices():
        services.append(
            service_entry(
                "disk_smart",
                smart_enabled,
                dev=dev,
                missing_requirements=smart_missing,
                note="requires non-interactive sudo permission for smartctl",
            )
        )
    for dev in detect_nvme_devices():
        services.append(
            service_entry(
                "nvme_smart",
                smart_enabled,
                dev=dev,
                missing_requirements=smart_missing,
                note="requires non-interactive sudo permission for smartctl",
            )
        )
    services.extend(detect_network_interfaces())
    services.append(
        service_entry(
            "docker_containers",
            False,
            include_label=DEFAULT_CONTAINER_INCLUDE_LABEL,
            expire_after=None,
            missing_requirements=[] if command_exists("docker") else ["docker"],
            note=(
                "disabled template; enable manually after confirming Docker socket "
                "access"
            ),
        )
    )
    if include_podman:
        services.extend(
            detected_podman_service_entries(
                rootless_podman_users,
                podman_socket=podman_socket,
                rootless_podman_uids=rootless_podman_uids,
                auto_discover_rootless_podman=auto_discover_rootless_podman,
            )
        )
    frigate_reachable = http_url_reachable(DEFAULT_FRIGATE_METRICS_URL)
    frigate_values: dict[str, Any] = {
        "url": DEFAULT_FRIGATE_METRICS_URL,
        "expire_after": None,
        "missing_requirements": [],
    }
    if not frigate_reachable:
        frigate_values["note"] = "disabled template; enable after Frigate is running"
    services.append(
        service_entry(
            "frigate",
            frigate_reachable,
            **frigate_values,
        )
    )
    services.append(
        service_entry(
            "asus_router_cpu",
            False,
            router_name="ASUS AX86U",
            ssh_user="<user>",
            ssh_ip="<ip-addr>",
            ssh_port=22,
            note="disabled template; edit SSH settings and enable manually",
        )
    )
    services.append(
        service_entry(
            "asus_router_connected_clients",
            False,
            router_name="ASUS AX86U",
            ssh_user="<user>",
            ssh_ip="<ip-addr>",
            ssh_port=22,
            note="disabled template; edit SSH settings and enable manually",
        )
    )
    services.append(
        service_entry(
            "asus_router_network",
            False,
            router_name="ASUS AX86U",
            dev="eth0",
            ssh_user="<user>",
            ssh_ip="<ip-addr>",
            ssh_port=22,
            note="disabled template; edit SSH settings and enable manually",
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ha_device_id": device,
        "timer_publish_discovery_config": DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG,
        "services": services,
    }
