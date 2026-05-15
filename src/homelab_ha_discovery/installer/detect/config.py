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
    detect_intel_qsv_gpu_devices,
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

def log_detection(
    component: str,
    detected: bool,
    detail: str,
    missing_requirements: list[str] | None = None,
) -> None:
    status = "detected" if detected else "not detected"
    print(f"{component} detection: {status}; {detail}")
    if missing_requirements:
        print(
            f"{component} detection: disabled; missing "
            + ", ".join(missing_requirements)
        )

def log_intel_qsv_detection(
    devices: dict[str, str | None],
    missing_requirements: list[str] | None = None,
) -> None:
    render_device = devices.get("render_device")
    drm_device = devices.get("drm_device")
    if not render_device and not drm_device:
        log_detection(
            "Intel QSV",
            False,
            "no /dev/dri/renderD* or card* devices",
        )
        return

    log_detection(
        "Intel QSV",
        not missing_requirements,
        f"render_device={render_device or '-'} drm_device={drm_device or '-'}",
        missing_requirements,
    )

def list_detail(name: str, values: list[object] | tuple[object, ...]) -> str:
    if not values:
        return f"no {name}"
    return f"{name}=" + ", ".join(str(value) for value in values)

def service_scope(service: dict[str, Any]) -> str:
    scope = service.get("scope")
    if isinstance(scope, str) and scope:
        return scope
    return "unknown"

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
    log_detection(
        "CPU",
        not cpu_missing,
        "tools=top,sensors" if not cpu_missing else "required tools missing",
        cpu_missing,
    )
    services.append(
        service_entry(
            "cpu",
            not cpu_missing,
            missing_requirements=cpu_missing,
        )
    )

    nvidia_exists = command_exists("nvidia-smi")
    nvidia_indexes = detect_nvidia_gpu_indexes() if nvidia_exists else []
    if nvidia_indexes:
        log_detection("NVIDIA GPU", True, list_detail("indexes", nvidia_indexes))
    elif nvidia_exists:
        log_detection("NVIDIA GPU", False, "nvidia-smi found but no GPUs detected")
    else:
        log_detection("NVIDIA GPU", False, "required tooling missing", ["nvidia-smi"])
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
    if amd_rocm_indexes:
        log_detection("AMD ROCm GPU", True, list_detail("indexes", amd_rocm_indexes))
    elif amd_rocm_exists:
        log_detection("AMD ROCm GPU", False, "rocm-smi found but no GPUs detected")
    else:
        log_detection("AMD ROCm GPU", False, "required tooling missing", ["rocm-smi"])
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

    intel_qsv_devices = detect_intel_qsv_gpu_devices()
    intel_qsv_dri_exists = bool(
        intel_qsv_devices.get("render_device") or intel_qsv_devices.get("drm_device")
    )
    if not intel_qsv_dri_exists:
        log_intel_qsv_detection(intel_qsv_devices)
    else:
        intel_qsv_missing = []
        if not intel_qsv_devices.get("render_device"):
            intel_qsv_missing.append("/dev/dri/renderD*")
        if not command_exists("intel_gpu_top"):
            intel_qsv_missing.append("intel_gpu_top")
        log_intel_qsv_detection(intel_qsv_devices, intel_qsv_missing)

        intel_qsv_values: dict[str, Any] = {
            "collector": "intel_qsv",
            "missing_requirements": intel_qsv_missing,
            "render_device": intel_qsv_devices.get("render_device"),
            "drm_device": intel_qsv_devices.get("drm_device"),
            "note": (
                "publishes Intel QSV media engine metrics in one timer loop"
                if not intel_qsv_missing
                else "disabled template; enable after Intel QSV tooling is available"
            ),
        }
        if intel_qsv_devices.get("render_device"):
            intel_qsv_values["gpu_indexes"] = [0]
        services.append(
            service_entry(
                "gpu",
                not intel_qsv_missing,
                **intel_qsv_values,
            )
        )

    disk_devices = detect_disk_devices()
    nvme_devices = detect_nvme_devices()
    smart_missing = [
        command
        for command in ("sudo", "smartctl")
        if not command_exists(command)
    ]
    smart_enabled = not smart_missing
    log_detection(
        "Disk SMART",
        bool(disk_devices) and smart_enabled,
        list_detail("devices", disk_devices),
        smart_missing if disk_devices else None,
    )
    log_detection(
        "NVMe SMART",
        bool(nvme_devices) and smart_enabled,
        list_detail("devices", nvme_devices),
        smart_missing if nvme_devices else None,
    )
    for dev in disk_devices:
        services.append(
            service_entry(
                "disk_smart",
                smart_enabled,
                dev=dev,
                missing_requirements=smart_missing,
                note="requires non-interactive sudo permission for smartctl",
            )
        )
    for dev in nvme_devices:
        services.append(
            service_entry(
                "nvme_smart",
                smart_enabled,
                dev=dev,
                missing_requirements=smart_missing,
                note="requires non-interactive sudo permission for smartctl",
            )
        )
    network_services = detect_network_interfaces()
    log_detection(
        "Network",
        bool(network_services),
        list_detail(
            "interfaces",
            [service.get("dev") for service in network_services],
        ),
    )
    services.extend(network_services)
    docker_exists = command_exists("docker")
    log_detection(
        "Docker",
        docker_exists,
        "command=docker" if docker_exists else "required tooling missing",
        None if docker_exists else ["docker"],
    )
    services.append(
        service_entry(
            "docker_containers",
            False,
            include_label=DEFAULT_CONTAINER_INCLUDE_LABEL,
            expire_after=None,
            missing_requirements=[] if docker_exists else ["docker"],
            note=(
                "disabled template; enable manually after confirming Docker socket "
                "access"
            ),
        )
    )
    if include_podman:
        podman_services = detected_podman_service_entries(
            rootless_podman_users,
            podman_socket=podman_socket,
            rootless_podman_uids=rootless_podman_uids,
            auto_discover_rootless_podman=auto_discover_rootless_podman,
        )
        enabled_podman_scopes = [
            service_scope(service)
            for service in podman_services
            if service.get("enabled")
        ]
        podman_missing = sorted(
            {
                requirement
                for service in podman_services
                for requirement in service.get("missing_requirements", [])
                if isinstance(requirement, str)
            }
        )
        log_detection(
            "Podman",
            bool(enabled_podman_scopes),
            list_detail("enabled_scopes", enabled_podman_scopes)
            if enabled_podman_scopes
            else "no running Podman containers detected",
            podman_missing if podman_missing else None,
        )
        services.extend(podman_services)
    else:
        log_detection("Podman", False, "disabled by config detect option")
    frigate_reachable = http_url_reachable(DEFAULT_FRIGATE_METRICS_URL)
    log_detection(
        "Frigate",
        frigate_reachable,
        f"metrics_url={DEFAULT_FRIGATE_METRICS_URL}",
    )
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
    log_detection(
        "ASUS router",
        False,
        "auto-detection is not supported; disabled templates generated",
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
