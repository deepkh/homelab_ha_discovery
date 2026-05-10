"""Install Debian host publishers as long-running systemd services."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any


DEFAULT_APP_DIR = Path("/opt/homelab-ha-discovery")
DEFAULT_CONFIG_DIR = Path("/etc/homelab-ha-discovery")
DEFAULT_SYSTEMD_DIR = Path("/etc/systemd/system")
CONFIG_FILENAME = "host-metrics.json"
MQTT_ENV_FILENAME = "mqtt.env"
SERVICE_PREFIX = "homelab-ha-discovery"
SCHEMA_VERSION = 1

DEFAULT_TIMERS = {
    "cpu": 5.0,
    "gpu": 5.0,
    "disk_smart": 60.0,
    "nvme_smart": 60.0,
    "network": 1.0,
}
DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG = 60.0
SCRIPT_BY_SERVICE_TYPE = {
    "cpu": "publish_cpu_metrics.py",
    "gpu": "publish_gpu_metrics.py",
    "disk_smart": "publish_sdx_metrics.py",
    "nvme_smart": "publish_nvme_metrics.py",
    "network": "publish_network_metrics.py",
}
DEBIAN_PACKAGES = (
    "python3",
    "python3-venv",
    "python3-pip",
    "procps",
    "lm-sensors",
    "smartmontools",
)
COPY_IGNORE_NAMES = {
    ".agents",
    ".codex",
    ".git",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "session",
}
UNIT_PART_RE = re.compile(r"[^A-Za-z0-9_.-]+")


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


@dataclass(frozen=True)
class UnitSpec:
    name: str
    content: str

    def path(self, systemd_dir: Path) -> Path:
        return systemd_dir / self.name


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_paths(args: argparse.Namespace) -> RuntimePaths:
    return RuntimePaths(
        app_dir=args.app_dir,
        config_dir=args.config_dir,
        systemd_dir=args.systemd_dir,
        source_root=repo_root(),
    )


def run_command(
    command: list[str],
    dry_run: bool,
    cwd: Path | None = None,
) -> None:
    printable = " ".join(shlex.quote(part) for part in command)
    if cwd is not None:
        printable = f"(cd {shlex.quote(str(cwd))} && {printable})"
    if dry_run:
        print(f"DRY RUN: {printable}")
        return
    subprocess.run(command, cwd=cwd, check=True)


def copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in COPY_IGNORE_NAMES or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def remove_existing_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def paths_are_same(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def install_system_packages(dry_run: bool) -> None:
    run_command(["apt-get", "update"], dry_run)
    run_command(["apt-get", "install", "-y", *DEBIAN_PACKAGES], dry_run)


def prepare_app_dir(paths: RuntimePaths, force_copy: bool, dry_run: bool) -> None:
    if paths_are_same(paths.source_root, paths.app_dir):
        print(f"App directory is already the current checkout: {paths.app_dir}")
        return

    if paths.app_dir.exists():
        if not force_copy:
            raise RuntimeError(
                f"{paths.app_dir} already exists; rerun with --force-copy to replace it"
            )
        if dry_run:
            print(f"DRY RUN: would remove existing app directory {paths.app_dir}")
        else:
            remove_existing_path(paths.app_dir)

    if dry_run:
        print(f"DRY RUN: would copy {paths.source_root} to {paths.app_dir}")
        return

    paths.app_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(paths.source_root, paths.app_dir, ignore=copy_ignore)


def create_virtualenv_and_install_requirements(
    paths: RuntimePaths,
    dry_run: bool,
) -> None:
    python3 = shutil.which("python3") or sys.executable
    venv_dir = paths.app_dir / ".venv"
    requirements_path = paths.app_dir / "requirements.txt"
    run_command([python3, "-m", "venv", str(venv_dir)], dry_run)
    run_command(
        [
            str(venv_dir / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "-r",
            str(requirements_path),
        ],
        dry_run,
    )


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


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def command_has_output(command: list[str], timeout: float = 5.0) -> bool:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def default_route_interfaces() -> set[str]:
    route_path = Path("/proc/net/route")
    interfaces: set[str] = set()
    try:
        lines = route_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return interfaces

    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        interface, destination, _gateway, flags = fields[:4]
        try:
            route_is_up = bool(int(flags, 16) & 0x2)
        except ValueError:
            route_is_up = False
        if destination == "00000000" and route_is_up:
            interfaces.add(interface)
    return interfaces


def detect_disk_devices() -> list[str]:
    sys_block = Path("/sys/block")
    if not sys_block.exists():
        return []
    devices = []
    for path in sorted(sys_block.iterdir(), key=lambda item: item.name):
        if not re.fullmatch(r"sd[a-z]+", path.name):
            continue
        dev_path = Path("/dev") / path.name
        if dev_path.exists():
            devices.append(str(dev_path))
    return devices


def detect_nvme_devices() -> list[str]:
    sys_nvme = Path("/sys/class/nvme")
    devices = []
    if sys_nvme.exists():
        for path in sorted(sys_nvme.iterdir(), key=lambda item: item.name):
            if not re.fullmatch(r"nvme\d+", path.name):
                continue
            dev_path = Path("/dev") / path.name
            if dev_path.exists():
                devices.append(str(dev_path))
    if devices:
        return devices

    return [
        str(path)
        for path in sorted(Path("/dev").glob("nvme[0-9]*"))
        if re.fullmatch(r"nvme\d+", path.name)
    ]


def detect_network_interfaces() -> list[dict[str, Any]]:
    sys_net = Path("/sys/class/net")
    if not sys_net.exists():
        return []
    default_routes = default_route_interfaces()
    interfaces = []
    for path in sorted(sys_net.iterdir(), key=lambda item: item.name):
        if path.name == "lo":
            continue
        operstate = read_text(path / "operstate") or "unknown"
        if default_routes:
            enabled = path.name in default_routes
            note = "default route interface" if enabled else "not a default route"
        else:
            enabled = operstate in {"up", "unknown"}
            note = f"operstate={operstate}"
        interfaces.append(
            {
                "type": "network",
                "enabled": enabled,
                "dev": path.name,
                "timer": DEFAULT_TIMERS["network"],
                "detected_operstate": operstate,
                "note": note,
            }
        )
    return interfaces


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
    return entry


def build_detected_config(device: str) -> dict[str, Any]:
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

    gpu_available = command_exists("nvidia-smi") and command_has_output(
        ["nvidia-smi", "-L"]
    )
    services.append(
        service_entry(
            "gpu",
            gpu_available,
            missing_requirements=[] if command_exists("nvidia-smi") else ["nvidia-smi"],
            note="publishes all detected NVIDIA GPUs",
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

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": Path(__file__).name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ha_device_id": device,
        "timer_publish_discovery_config": DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG,
        "services": services,
    }


def write_detected_config(
    paths: RuntimePaths,
    device: str,
    force: bool,
    dry_run: bool,
    force_option: str,
) -> None:
    config = build_detected_config(device)
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
        gpu_index = service.get("gpu_index")
        if gpu_index is None:
            return "gpu"
        return f"gpu{gpu_index}"
    if service_type in {"disk_smart", "nvme_smart"}:
        return Path(require_string(service.get("dev"), f"{service_type} dev")).name
    if service_type == "network":
        return require_string(service.get("dev"), "network dev")
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
    else:
        raise RuntimeError(f"unsupported service type: {service_type}")
    return f"{SERVICE_PREFIX}-{device_part}-{suffix}.service"


def service_description(device: str, service: dict[str, Any]) -> str:
    service_type = require_string(service.get("type"), "service type")
    component = service_component(service)
    if service_type == "cpu":
        return f"Homelab HA Discovery CPU metrics for {device}"
    if service_type == "gpu":
        return f"Homelab HA Discovery NVIDIA GPU metrics for {device}"
    if service_type == "disk_smart":
        return f"Homelab HA Discovery disk SMART metrics for {device} {component}"
    if service_type == "nvme_smart":
        return f"Homelab HA Discovery NVMe SMART metrics for {device} {component}"
    if service_type == "network":
        return f"Homelab HA Discovery network metrics for {device} {component}"
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
    if service_type == "gpu" and service.get("gpu_index") is not None:
        command.extend(["--gpu", str(service["gpu_index"])])
    if service_type in {"disk_smart", "nvme_smart", "network"}:
        command.extend(["--dev", require_string(service.get("dev"), "dev")])
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
            "Type=simple",
            f"WorkingDirectory={systemd_arg(paths.app_dir)}",
            f"EnvironmentFile=-{systemd_arg(paths.mqtt_env_path)}",
            f"ExecStart={command}",
            "Restart=always",
            "RestartSec=10s",
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


def command_bootstrap(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        if args.install_system_packages:
            install_system_packages(args.dry_run)
        prepare_app_dir(paths, args.force_copy, args.dry_run)
        create_virtualenv_and_install_requirements(paths, args.dry_run)
        ensure_config_dir(paths, args.dry_run)
        ensure_mqtt_env(paths, args.dry_run)
        write_detected_config(
            paths,
            args.device,
            force=args.force_config,
            dry_run=args.dry_run,
            force_option="--force-config",
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_detect(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        ensure_config_dir(paths, args.dry_run)
        write_detected_config(
            paths,
            args.device,
            force=args.force,
            dry_run=args.dry_run,
            force_option="--force",
        )
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_install(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = build_unit_specs(paths, load_config(paths))
        write_units(paths, units, args.dry_run)
        run_command(["systemctl", "daemon-reload"], args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_enable(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        if not paths.mqtt_env_path.exists() and not args.allow_missing_mqtt_env:
            raise RuntimeError(
                f"{paths.mqtt_env_path} is missing; create it before enabling "
                "services or pass --allow-missing-mqtt-env"
            )
        units = build_unit_specs(paths, load_config(paths))
        if not units:
            raise RuntimeError("no enabled services found in config")
        missing_units = [
            unit.name
            for unit in units
            if not unit.path(paths.systemd_dir).exists()
        ]
        if missing_units and not args.dry_run:
            raise RuntimeError(
                "systemd unit file(s) missing; run install first: "
                + ", ".join(missing_units)
            )

        run_command(["systemctl", "daemon-reload"], args.dry_run)
        command = ["systemctl", "enable"]
        if args.now:
            command.append("--now")
        command.extend(unit.name for unit in units)
        run_command(command, args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_status(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = build_unit_specs(paths, load_config(paths))
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not units:
        print(f"No enabled services in {paths.config_path}")
        return 0

    unit_names = [unit.name for unit in units]
    print(f"Config: {paths.config_path}")
    print("Generated unit names:")
    for unit_name in unit_names:
        print(f"  {unit_name}")
    print("Useful commands:")
    print("  systemctl status " + " ".join(shlex.quote(name) for name in unit_names))
    journal_units = " ".join(f"-u {shlex.quote(name)}" for name in unit_names)
    print("  journalctl -f " + journal_units)
    print("  systemctl restart " + " ".join(shlex.quote(name) for name in unit_names))
    return 0


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--app-dir",
        type=Path,
        default=DEFAULT_APP_DIR,
        help=f"Installed application directory. Default: {DEFAULT_APP_DIR}",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help=f"Configuration directory. Default: {DEFAULT_CONFIG_DIR}",
    )
    parser.add_argument(
        "--systemd-dir",
        type=Path,
        default=DEFAULT_SYSTEMD_DIR,
        help=f"systemd unit directory. Default: {DEFAULT_SYSTEMD_DIR}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes and commands without changing the system.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="Copy the checkout, create a venv, and write detected host config.",
    )
    add_common_options(bootstrap_parser)
    bootstrap_parser.add_argument(
        "--ha-device-id",
        dest="device",
        required=True,
        help="Stable Home Assistant/MQTT device identity.",
    )
    bootstrap_parser.add_argument(
        "--force-copy",
        action="store_true",
        help=f"Replace {DEFAULT_APP_DIR} if it already exists.",
    )
    bootstrap_parser.add_argument(
        "--force-config",
        action="store_true",
        help="Replace an existing host-metrics.json during bootstrap.",
    )
    bootstrap_parser.add_argument(
        "--install-system-packages",
        action="store_true",
        help="Install Debian packages with apt-get before bootstrapping.",
    )
    bootstrap_parser.set_defaults(func=command_bootstrap)

    detect_parser = subparsers.add_parser(
        "detect",
        help="Detect local host metrics and write host-metrics.json.",
    )
    add_common_options(detect_parser)
    detect_parser.add_argument(
        "--ha-device-id",
        dest="device",
        required=True,
        help="Stable Home Assistant/MQTT device identity.",
    )
    detect_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing host-metrics.json.",
    )
    detect_parser.set_defaults(func=command_detect)

    install_parser = subparsers.add_parser(
        "install",
        help="Generate systemd service files from host-metrics.json.",
    )
    add_common_options(install_parser)
    install_parser.set_defaults(func=command_install)

    enable_parser = subparsers.add_parser(
        "enable",
        help="Enable generated systemd services.",
    )
    add_common_options(enable_parser)
    enable_parser.add_argument(
        "--now",
        action="store_true",
        help="Start the generated services immediately after enabling them.",
    )
    enable_parser.add_argument(
        "--allow-missing-mqtt-env",
        action="store_true",
        help="Enable services even if mqtt.env does not exist.",
    )
    enable_parser.set_defaults(func=command_enable)

    status_parser = subparsers.add_parser(
        "status",
        help="Print generated unit names and useful systemctl commands.",
    )
    add_common_options(status_parser)
    status_parser.set_defaults(func=command_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
