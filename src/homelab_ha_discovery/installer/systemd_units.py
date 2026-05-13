"""systemd unit rendering for homelab-ha-discovery publishers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from homelab_ha_discovery.installer.config_io import (
    DEFAULT_FRIGATE_METRICS_URL,
    DEFAULT_GPU_COLLECTOR,
    DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG,
    DEFAULT_TIMERS,
    GPU_COLLECTOR_ALIASES,
    GPU_COLLECTOR_LABELS,
    RuntimePaths,
    SCRIPT_BY_SERVICE_TYPE,
    SERVICE_PREFIX,
    SKIP_ENV_FILES_ENV,
    require_non_negative_seconds,
    require_positive_seconds,
    require_ssh_port,
    require_string,
    require_timer,
    require_uid,
)
from homelab_ha_discovery.installer.detect.podman import (
    podman_scope_from_value,
    user_uid,
)


UNIT_PART_RE = re.compile(r"[^A-Za-z0-9_.-]+")

@dataclass(frozen=True)
class UnitSpec:
    name: str
    content: str

    def path(self, systemd_dir: Path) -> Path:
        return systemd_dir / self.name

def normalize_gpu_collector(value: object) -> str:
    if value is None:
        return DEFAULT_GPU_COLLECTOR
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("gpu collector must be a non-empty string")
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in GPU_COLLECTOR_ALIASES:
        choices = ", ".join(sorted(GPU_COLLECTOR_ALIASES))
        raise RuntimeError(
            f"unsupported gpu collector: {value}; expected one of {choices}"
        )
    return GPU_COLLECTOR_ALIASES[normalized]

def container_include_labels(service: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    include_label = service.get("include_label")
    if include_label is not None:
        labels.append(require_string(include_label, "include_label"))

    include_labels = service.get("include_labels")
    if include_labels is None:
        return labels
    if not isinstance(include_labels, list):
        raise RuntimeError("include_labels must be a list")
    for index, value in enumerate(include_labels):
        labels.append(require_string(value, f"include_labels[{index}]"))
    return labels

def podman_scope_for_service(service: dict[str, Any]) -> str:
    if service.get("scope") is not None:
        return podman_scope_from_value(require_string(service.get("scope"), "scope"))
    if service.get("rootless_user") is not None:
        return podman_scope_from_value(
            require_string(service.get("rootless_user"), "rootless_user")
        )
    return "root"

def podman_rootless_uid_for_service(service: dict[str, Any]) -> int:
    if service.get("rootless_uid") is not None:
        return require_uid(service.get("rootless_uid"), "rootless_uid")

    user = require_string(service.get("rootless_user"), "rootless_user")
    uid = user_uid(user)
    if uid is None:
        raise RuntimeError(f"rootless_user does not exist: {user}")
    return uid

def require_gpu_index(value: object, name: str) -> int:
    try:
        index = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if isinstance(value, float) and not value.is_integer():
        raise RuntimeError(f"{name} must be an integer")
    if index < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return index

def gpu_indexes_for_service(service: dict[str, Any]) -> list[int]:
    has_gpu_index = service.get("gpu_index") is not None
    has_gpu_indexes = service.get("gpu_indexes") is not None
    if has_gpu_index and has_gpu_indexes:
        raise RuntimeError("gpu service cannot set both gpu_index and gpu_indexes")
    if has_gpu_index:
        return [require_gpu_index(service.get("gpu_index"), "gpu_index")]
    if not has_gpu_indexes:
        return []

    values = service.get("gpu_indexes")
    if not isinstance(values, list) or not values:
        raise RuntimeError("gpu_indexes must be a non-empty list")

    indexes: list[int] = []
    for index, value in enumerate(values):
        gpu_index = require_gpu_index(value, f"gpu_indexes[{index}]")
        if gpu_index not in indexes:
            indexes.append(gpu_index)
    return indexes

def discovery_timer_for_service(
    config: dict[str, Any],
    service: dict[str, Any],
) -> float | None:
    if "timer_publish_discovery_config" in service:
        value = service["timer_publish_discovery_config"]
    else:
        value = config.get(
            "timer_publish_discovery_config",
            DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG,
        )
    if value is None:
        return None
    return require_positive_seconds(value, "timer_publish_discovery_config")

def unit_part(value: str) -> str:
    normalized = UNIT_PART_RE.sub("-", value.strip().strip("/")).strip("-")
    if not normalized:
        raise RuntimeError(f"could not derive systemd unit name part from {value!r}")
    return normalized.lower()

def systemd_arg(value: object) -> str:
    text = str(value).replace("%", "%%")
    if not text:
        return '""'
    if re.search(r"\s|[\"'\\]", text):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text

def service_component(service: dict[str, Any]) -> str:
    service_type = require_string(service.get("type"), "service type")
    if service_type == "cpu":
        return "cpu"
    if service_type == "gpu":
        collector = normalize_gpu_collector(service.get("collector"))
        indexes = gpu_indexes_for_service(service)
        gpu_component = (
            "gpu"
            if not indexes
            else "-".join(f"gpu{gpu_index}" for gpu_index in indexes)
        )
        if collector == "nvidia":
            return gpu_component
        return f"{GPU_COLLECTOR_LABELS[collector]} {gpu_component}"
    if service_type in {"disk_smart", "nvme_smart"}:
        return Path(require_string(service.get("dev"), f"{service_type} dev")).name
    if service_type == "network":
        return require_string(service.get("dev"), "network dev")
    if service_type == "docker_containers":
        return "docker-containers"
    if service_type == "podman_containers":
        return f"podman-containers-{podman_scope_for_service(service)}"
    if service_type == "frigate":
        return "frigate"
    if service_type == "asus_router_network":
        return (
            f"{require_string(service.get('router_name'), 'router_name')} "
            f"{require_string(service.get('dev'), 'asus_router_network dev')}"
        )
    if service_type in {"asus_router_cpu", "asus_router_connected_clients"}:
        return require_string(service.get("router_name"), "router_name")
    raise RuntimeError(f"unsupported service type: {service_type}")

def service_unit_name(device: str, service: dict[str, Any]) -> str:
    service_type = require_string(service.get("type"), "service type")
    device_part = unit_part(device)
    component = unit_part(service_component(service))
    if service_type == "cpu":
        suffix = "cpu"
    elif service_type == "gpu":
        suffix = component
    elif service_type == "disk_smart":
        suffix = f"disk-{component}"
    elif service_type == "nvme_smart":
        suffix = f"nvme-{component}"
    elif service_type == "network":
        suffix = f"network-{component}"
    elif service_type == "docker_containers":
        suffix = "docker-containers"
    elif service_type == "podman_containers":
        suffix = component
    elif service_type == "frigate":
        suffix = "frigate"
    elif service_type == "asus_router_cpu":
        suffix = f"asus-router-cpu-{component}"
    elif service_type == "asus_router_connected_clients":
        suffix = f"asus-router-connected-clients-{component}"
    elif service_type == "asus_router_network":
        suffix = f"asus-router-network-{component}"
    else:
        raise RuntimeError(f"unsupported service type: {service_type}")
    return f"{SERVICE_PREFIX}-{device_part}-{suffix}.service"

def service_description(device: str, service: dict[str, Any]) -> str:
    service_type = require_string(service.get("type"), "service type")
    component = service_component(service)
    if service_type == "cpu":
        return f"Homelab HA Discovery CPU metrics for {device}"
    if service_type == "gpu":
        collector = normalize_gpu_collector(service.get("collector"))
        return (
            "Homelab HA Discovery "
            f"{GPU_COLLECTOR_LABELS[collector]} GPU metrics for {device}"
        )
    if service_type == "disk_smart":
        return f"Homelab HA Discovery disk SMART metrics for {device} {component}"
    if service_type == "nvme_smart":
        return f"Homelab HA Discovery NVMe SMART metrics for {device} {component}"
    if service_type == "network":
        return f"Homelab HA Discovery network metrics for {device} {component}"
    if service_type == "docker_containers":
        return f"Homelab HA Discovery Docker container metrics for {device}"
    if service_type == "podman_containers":
        return (
            "Homelab HA Discovery Podman container metrics "
            f"for {device} {podman_scope_for_service(service)}"
        )
    if service_type == "frigate":
        return f"Homelab HA Discovery Frigate metrics for {device}"
    if service_type == "asus_router_cpu":
        return f"Homelab HA Discovery ASUS router CPU metrics for {device} {component}"
    if service_type == "asus_router_connected_clients":
        return (
            "Homelab HA Discovery ASUS router connected-client metrics "
            f"for {device} {component}"
        )
    if service_type == "asus_router_network":
        return (
            "Homelab HA Discovery ASUS router network metrics "
            f"for {device} {component}"
        )
    raise RuntimeError(f"unsupported service type: {service_type}")

def service_command(
    paths: RuntimePaths,
    device: str,
    service: dict[str, Any],
    discovery_timer: float | None,
) -> list[str]:
    service_type = require_string(service.get("type"), "service type")
    script_name = SCRIPT_BY_SERVICE_TYPE.get(service_type)
    if script_name is None:
        raise RuntimeError(f"unsupported service type: {service_type}")

    timer = require_timer(service.get("timer"), service_type)
    command = [
        str(paths.app_dir / ".venv" / "bin" / "python"),
        str(paths.app_dir / "src" / "homelab_ha_discovery" / "scripts" / script_name),
        "--ha-device-id",
        device,
    ]
    if service_type == "gpu":
        collector = normalize_gpu_collector(service.get("collector"))
        if collector != DEFAULT_GPU_COLLECTOR:
            command.extend(["--collector", collector])
        for gpu_index in gpu_indexes_for_service(service):
            command.extend(["--gpu", str(gpu_index)])
    if service_type in {"disk_smart", "nvme_smart", "network"}:
        command.extend(["--dev", require_string(service.get("dev"), "dev")])
    if service_type == "docker_containers":
        if service.get("all"):
            command.append("--all")
        for label in container_include_labels(service):
            command.extend(["--include-label", label])
        if service.get("docker_command") is not None:
            command.extend(
                [
                    "--docker-command",
                    require_string(service.get("docker_command"), "docker_command"),
                ]
            )
        if service.get("debug"):
            command.append("--debug")
    if service_type == "podman_containers":
        if service.get("all"):
            command.append("--all")
        for label in container_include_labels(service):
            command.extend(["--include-label", label])
        if service.get("podman_command") is not None:
            command.extend(
                [
                    "--podman-command",
                    require_string(service.get("podman_command"), "podman_command"),
                ]
            )
        command.extend(["--podman-scope", podman_scope_for_service(service)])
        if service.get("debug"):
            command.append("--debug")
    if service_type == "frigate":
        command.extend(
            [
                "--url",
                require_string(
                    service.get("url", DEFAULT_FRIGATE_METRICS_URL),
                    "url",
                ),
            ]
        )
        if service.get("debug"):
            command.append("--debug")
    if service_type == "asus_router_network":
        command.extend(
            [
                "--router-name",
                require_string(service.get("router_name"), "router_name"),
                "--dev",
                require_string(service.get("dev"), "dev"),
                "--ssh-user",
                require_string(service.get("ssh_user"), "ssh_user"),
                "--ssh-ip",
                require_string(service.get("ssh_ip"), "ssh_ip"),
                "--ssh-port",
                str(require_ssh_port(service.get("ssh_port"))),
            ]
        )
    if service_type in {"asus_router_cpu", "asus_router_connected_clients"}:
        command.extend(
            [
                "--router-name",
                require_string(service.get("router_name"), "router_name"),
                "--ssh-user",
                require_string(service.get("ssh_user"), "ssh_user"),
                "--ssh-ip",
                require_string(service.get("ssh_ip"), "ssh_ip"),
                "--ssh-port",
                str(require_ssh_port(service.get("ssh_port"))),
            ]
        )
    if service_type == "asus_router_connected_clients":
        if service.get("client_list_command") is not None:
            command.extend(
                [
                    "--client-list-command",
                    require_string(
                        service.get("client_list_command"),
                        "client_list_command",
                    ),
                ]
            )
    if service_type == "asus_router_cpu":
        if service.get("top_command") is not None:
            command.extend(
                [
                    "--top-command",
                    require_string(service.get("top_command"), "top_command"),
                ]
            )
        if service.get("temperature_command") is not None:
            command.extend(
                [
                    "--temperature-command",
                    require_string(
                        service.get("temperature_command"),
                        "temperature_command",
                    ),
                ]
            )
    if service_type == "asus_router_network":
        if service.get("network_command") is not None:
            command.extend(
                [
                    "--network-command",
                    require_string(service.get("network_command"), "network_command"),
                ]
            )
    if service.get("expire_after") is not None:
        command.extend(
            [
                "--expire-after",
                str(
                    require_non_negative_seconds(
                        service.get("expire_after"),
                        "expire_after",
                    )
                ),
            ]
        )
    command.extend(["--timer", str(timer)])

    if discovery_timer is not None:
        command.extend(
            [
                "--timer-publish-discovery-config",
                str(discovery_timer),
            ]
        )
    return command

def render_unit(
    paths: RuntimePaths,
    device: str,
    service: dict[str, Any],
    discovery_timer: float | None,
) -> UnitSpec:
    name = service_unit_name(device, service)
    description = service_description(device, service)
    command = " ".join(
        systemd_arg(arg)
        for arg in service_command(paths, device, service, discovery_timer)
    )
    service_lines = ["Type=simple"]
    if require_string(service.get("type"), "service type") == "podman_containers":
        if service.get("podman_socket") is not None:
            podman_socket = require_string(
                service.get("podman_socket"),
                "podman_socket",
            )
            service_lines.append(
                f"Environment={systemd_arg(f'CONTAINER_HOST={podman_socket}')}"
            )
        if service.get("rootless_user") is not None:
            rootless_user = require_string(
                service.get("rootless_user"),
                "rootless_user",
            )
            rootless_uid = podman_rootless_uid_for_service(service)
            service_lines.extend(
                (
                    f"User={rootless_user}",
                    f"Environment=XDG_RUNTIME_DIR=/run/user/{rootless_uid}",
                )
            )
    service_lines.extend(
        (
            f"WorkingDirectory={systemd_arg(paths.app_dir)}",
            f"EnvironmentFile=-{systemd_arg(paths.mqtt_env_path)}",
            f"Environment={SKIP_ENV_FILES_ENV}=1",
            f"ExecStart={command}",
            "Restart=always",
            "RestartSec=60s",
        )
    )
    content = "\n".join(
        (
            "# Generated by homelab-ha-discovery.",
            "# Edit host-metrics.json and rerun install to regenerate this unit.",
            "[Unit]",
            f"Description={description}",
            "Wants=network-online.target",
            "After=network-online.target",
            "",
            "[Service]",
            *service_lines,
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        )
    )
    return UnitSpec(name=name, content=content)

def enabled_services(config: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    device = require_string(config.get("ha_device_id"), "ha_device_id")
    services = config.get("services")
    if not isinstance(services, list):
        raise RuntimeError("services must be a list")
    enabled = [
        service
        for service in services
        if isinstance(service, dict) and service.get("enabled", True)
    ]
    return device, enabled

def build_unit_specs(paths: RuntimePaths, config: dict[str, Any]) -> list[UnitSpec]:
    device, services = enabled_services(config)
    return [
        render_unit(
            paths,
            device,
            service,
            discovery_timer_for_service(config, service),
        )
        for service in services
    ]

def write_units(paths: RuntimePaths, units: list[UnitSpec], dry_run: bool) -> None:
    if not units:
        raise RuntimeError("no enabled services found in config")
    if dry_run:
        for unit in units:
            print(f"DRY RUN: would write {unit.path(paths.systemd_dir)}")
            print(unit.content)
        return

    paths.systemd_dir.mkdir(parents=True, exist_ok=True)
    for unit in units:
        unit_path = unit.path(paths.systemd_dir)
        unit_path.write_text(unit.content, encoding="utf-8")
        unit_path.chmod(0o644)
        print(f"Wrote systemd unit: {unit_path}")
