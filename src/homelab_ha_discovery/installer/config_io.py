"""Configuration and path helpers for the Debian host systemd installer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any


DEFAULT_APP_DIR = Path("/opt/homelab-ha-discovery")
DEFAULT_CONFIG_DIR = Path("/etc/homelab-ha-discovery")
DEFAULT_SYSTEMD_DIR = Path("/etc/systemd/system")
CONFIG_FILENAME = "host-metrics.json"
MQTT_ENV_FILENAME = "mqtt.env"
SKIP_ENV_FILES_ENV = "HOMELAB_HA_DISCOVERY_SKIP_ENV_FILES"
SERVICE_PREFIX = "homelab-ha-discovery"
SCHEMA_VERSION = 1

DEFAULT_TIMERS = {
    "cpu": 5.0,
    "gpu": 5.0,
    "disk_smart": 60.0,
    "nvme_smart": 60.0,
    "network": 1.0,
    "docker_containers": 60.0,
    "podman_containers": 60.0,
    "frigate": 10.0,
    "asus_router_cpu": 1.0,
    "asus_router_connected_clients": 1.0,
    "asus_router_network": 1.0,
}
DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG = 60.0
DEFAULT_FRIGATE_METRICS_URL = "http://127.0.0.1:5000/api/metrics"
DEFAULT_CONTAINER_INCLUDE_LABEL = "homelab-ha-discovery.enabled=true"
FRIGATE_DETECT_TIMEOUT_SECONDS = 2.0
DEFAULT_GPU_COLLECTOR = "nvidia"
GPU_COLLECTOR_ALIASES = {
    "nvidia": "nvidia",
    "amd": "amd_rocm",
    "rocm": "amd_rocm",
    "amd_rocm": "amd_rocm",
    "amd-rocm": "amd_rocm",
    "intel": "intel_qsv",
    "qsv": "intel_qsv",
    "intel_qsv": "intel_qsv",
    "intel-qsv": "intel_qsv",
}
GPU_COLLECTOR_LABELS = {
    "nvidia": "NVIDIA",
    "amd_rocm": "AMD ROCm",
    "intel_qsv": "Intel QSV",
}
SCRIPT_BY_SERVICE_TYPE = {
    "cpu": "publish_cpu_metrics.py",
    "gpu": "publish_gpu_metrics.py",
    "disk_smart": "publish_sdx_metrics.py",
    "nvme_smart": "publish_nvme_metrics.py",
    "network": "publish_network_metrics.py",
    "docker_containers": "publish_docker_container_metrics.py",
    "podman_containers": "publish_podman_container_metrics.py",
    "frigate": "publish_frigate_metrics.py",
    "asus_router_cpu": "publish_asus_router_cpu_metrics.py",
    "asus_router_connected_clients": (
        "publish_asus_router_connected_clients_metrics.py"
    ),
    "asus_router_network": "publish_asus_router_network_metrics.py",
}

@dataclass(frozen=True)
class RuntimePaths:
    app_dir: Path
    config_dir: Path
    systemd_dir: Path
    source_root: Path

    @property
    def config_path(self) -> Path:
        return self.config_dir / CONFIG_FILENAME

    @property
    def mqtt_env_path(self) -> Path:
        return self.config_dir / MQTT_ENV_FILENAME

def build_paths(args: argparse.Namespace) -> RuntimePaths:
    return RuntimePaths(
        app_dir=args.app_dir,
        config_dir=args.config_dir,
        systemd_dir=args.systemd_dir,
        source_root=repo_root(),
    )


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

def ensure_config_dir(paths: RuntimePaths, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY RUN: would create config directory {paths.config_dir}")
        return
    paths.config_dir.mkdir(parents=True, exist_ok=True)

def mqtt_env_template_text() -> str:
    return "\n".join(
        (
            "# MQTT settings for homelab-ha-discovery.",
            "# Edit this file before enabling generated services.",
            "HA_MQTT_HOST=mqtt-server-ip",
            "HA_MQTT_PORT=1883",
            "HA_MQTT_TOPIC_PREFIX=homelab-ha-discovery",
            "# HA_MQTT_USERNAME=your-user",
            "# HA_MQTT_PASSWORD=your-password",
            "",
        )
    )

def ensure_mqtt_env(paths: RuntimePaths, dry_run: bool) -> bool:
    if paths.mqtt_env_path.exists():
        print(f"MQTT environment file found: {paths.mqtt_env_path}")
        return True

    if dry_run:
        print(f"DRY RUN: would write MQTT environment file {paths.mqtt_env_path}")
    else:
        paths.mqtt_env_path.write_text(mqtt_env_template_text(), encoding="utf-8")
        paths.mqtt_env_path.chmod(0o600)
        print(f"Wrote MQTT environment file: {paths.mqtt_env_path}")

    print(
        "WARNING: edit MQTT settings before services are enabled: "
        f"{paths.mqtt_env_path}",
        file=sys.stderr,
    )
    return False

def service_entry(
    service_type: str,
    enabled: bool,
    **values: Any,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": service_type,
        "enabled": enabled,
        "timer": DEFAULT_TIMERS[service_type],
    }
    entry.update(values)
    entry.setdefault("expire_after", None)
    return entry

def write_detected_config(
    paths: RuntimePaths,
    device: str,
    rootless_podman_users: list[str] | tuple[str, ...],
    force: bool,
    dry_run: bool,
    force_option: str,
    include_podman: bool = True,
    podman_socket: str | None = None,
    rootless_podman_uids: list[int] | tuple[int, ...] = (),
    auto_discover_rootless_podman: bool = False,
) -> None:
    from homelab_ha_discovery.installer.detect.config import build_detected_config

    config = build_detected_config(
        device,
        rootless_podman_users=rootless_podman_users,
        include_podman=include_podman,
        podman_socket=podman_socket,
        rootless_podman_uids=rootless_podman_uids,
        auto_discover_rootless_podman=auto_discover_rootless_podman,
    )
    if paths.config_path.exists() and not force:
        print(
            f"Keeping existing config: {paths.config_path}. "
            f"Use {force_option} to replace it."
        )
        return

    rendered = json.dumps(config, indent=2) + "\n"
    if dry_run:
        print(f"DRY RUN: would write detected config {paths.config_path}")
        print(rendered)
        return

    paths.config_path.write_text(rendered, encoding="utf-8")
    paths.config_path.chmod(0o644)
    print(f"Wrote detected metrics config: {paths.config_path}")

def load_config(paths: RuntimePaths) -> dict[str, Any]:
    try:
        with paths.config_path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"config not found: {paths.config_path}; run detect or bootstrap first"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {paths.config_path}: {exc}") from exc

    if not isinstance(config, dict):
        raise RuntimeError(f"config must be a JSON object: {paths.config_path}")
    return config

def require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{name} is required")
    return value.strip()

def require_timer(value: object, service_type: str) -> float:
    if value is None:
        return DEFAULT_TIMERS[service_type]
    return require_positive_seconds(value, f"timer for {service_type}")

def require_positive_seconds(value: object, name: str) -> float:
    try:
        timer = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not math.isfinite(timer) or timer <= 0:
        raise RuntimeError(f"{name} must be greater than 0")
    return timer

def require_non_negative_seconds(value: object, name: str) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not math.isfinite(seconds) or seconds < 0:
        raise RuntimeError(f"{name} must be greater than or equal to 0")
    return seconds

def require_ssh_port(value: object) -> int:
    if value is None:
        return 22
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("ssh_port must be an integer") from exc
    if isinstance(value, float) and not value.is_integer():
        raise RuntimeError("ssh_port must be an integer")
    if port <= 0 or port > 65535:
        raise RuntimeError("ssh_port must be between 1 and 65535")
    return port

def require_uid(value: object, name: str) -> int:
    try:
        uid = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if isinstance(value, float) and not value.is_integer():
        raise RuntimeError(f"{name} must be an integer")
    if uid < 0:
        raise RuntimeError(f"{name} must be zero or greater")
    return uid


def command_detect(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        ensure_config_dir(paths, args.dry_run)
        write_detected_config(
            paths,
            args.device,
            rootless_podman_users=args.rootless_podman_user,
            force=args.force,
            dry_run=args.dry_run,
            force_option="--force",
            include_podman=getattr(args, "include_podman", True),
            podman_socket=getattr(args, "podman_socket", None),
            rootless_podman_uids=getattr(args, "rootless_podman_uid", ()),
            auto_discover_rootless_podman=getattr(
                args,
                "auto_discover_rootless_podman",
                False,
            ),
        )
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
