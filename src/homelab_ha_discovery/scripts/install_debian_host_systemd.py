"""Install Debian host publishers as long-running systemd services."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import shutil
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from homelab_ha_discovery.installer.app_install import (
    COPY_IGNORE_NAMES,
    DEBIAN_PACKAGES,
    copy_ignore,
    create_virtualenv_and_install_requirements,
    install_system_packages,
    paths_are_same,
    prepare_app_dir,
    remove_existing_path,
    repo_root,
)
from homelab_ha_discovery.installer.config_io import (
    CONFIG_FILENAME,
    DEFAULT_APP_DIR,
    DEFAULT_CONFIG_DIR,
    DEFAULT_CONTAINER_INCLUDE_LABEL,
    DEFAULT_FRIGATE_METRICS_URL,
    DEFAULT_GPU_COLLECTOR,
    DEFAULT_SYSTEMD_DIR,
    DEFAULT_TIMER_PUBLISH_DISCOVERY_CONFIG,
    DEFAULT_TIMERS,
    FRIGATE_DETECT_TIMEOUT_SECONDS,
    GPU_COLLECTOR_ALIASES,
    GPU_COLLECTOR_LABELS,
    MQTT_ENV_FILENAME,
    RuntimePaths,
    SCHEMA_VERSION,
    SCRIPT_BY_SERVICE_TYPE,
    SERVICE_PREFIX,
    SKIP_ENV_FILES_ENV,
    build_paths,
    command_detect,
    ensure_config_dir,
    ensure_mqtt_env,
    load_config,
    mqtt_env_template_text,
    require_non_negative_seconds,
    require_positive_seconds,
    require_ssh_port,
    require_string,
    require_timer,
    require_uid,
    service_entry,
    write_detected_config,
)
from homelab_ha_discovery.installer.detect.commands import (
    command_exists,
    command_has_output,
    command_output,
)
from homelab_ha_discovery.installer.detect.frigate import http_url_reachable
from homelab_ha_discovery.installer.detect.gpu import (
    detect_amd_rocm_gpu_indexes,
    detect_intel_qsv_gpu_devices,
    detect_nvidia_gpu_indexes,
    parse_amd_rocm_gpu_indexes,
    parse_nvidia_gpu_indexes,
)
from homelab_ha_discovery.installer.detect.network import (
    default_route_interfaces,
    detect_network_interfaces,
    read_text,
)
from homelab_ha_discovery.installer.detect.podman import (
    PODMAN_SCOPE_RE,
    detect_podman_has_running_containers,
    detected_podman_service_entries,
    podman_ps_command,
    podman_scope_from_value,
    unique_rootless_podman_users,
    user_uid,
)
from homelab_ha_discovery.installer.detect.storage import (
    detect_disk_devices,
    detect_nvme_devices,
)
from homelab_ha_discovery.installer.systemd_manager import (
    existing_generated_unit_paths,
    load_configured_units,
    maybe_remove_existing_generated_units,
    prompt_remove_existing_generated_units,
    remove_existing_generated_units,
    require_installed_unit_files,
    run_command,
    unit_names,
    unit_names_from_paths,
)
from homelab_ha_discovery.installer.systemd_units import (
    UNIT_PART_RE,
    UnitSpec,
    build_unit_specs,
    container_include_labels,
    discovery_timer_for_service,
    enabled_services,
    gpu_indexes_for_service,
    normalize_gpu_collector,
    podman_rootless_uid_for_service,
    podman_scope_for_service,
    render_unit,
    require_gpu_index,
    service_command,
    service_component,
    service_description,
    service_unit_name,
    systemd_arg,
    unit_part,
    write_units,
)


@contextmanager
def _patched_module_attrs(replacements):
    originals = []
    for module, name, value in replacements:
        originals.append((module, name, getattr(module, name)))
        setattr(module, name, value)
    try:
        yield
    finally:
        for module, name, value in reversed(originals):
            setattr(module, name, value)


def build_detected_config(
    device: str,
    rootless_podman_users: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    from homelab_ha_discovery.installer.detect import config as detect_config
    from homelab_ha_discovery.installer.detect import podman as detect_podman

    replacements = [
        (detect_config, "command_exists", command_exists),
        (detect_config, "detect_nvidia_gpu_indexes", detect_nvidia_gpu_indexes),
        (detect_config, "detect_amd_rocm_gpu_indexes", detect_amd_rocm_gpu_indexes),
        (detect_config, "detect_intel_qsv_gpu_devices", detect_intel_qsv_gpu_devices),
        (detect_config, "detect_disk_devices", detect_disk_devices),
        (detect_config, "detect_nvme_devices", detect_nvme_devices),
        (detect_config, "detect_network_interfaces", detect_network_interfaces),
        (detect_config, "http_url_reachable", http_url_reachable),
        (detect_podman, "command_exists", command_exists),
        (detect_podman, "command_has_output", command_has_output),
        (
            detect_podman,
            "detect_podman_has_running_containers",
            detect_podman_has_running_containers,
        ),
        (detect_podman, "user_uid", user_uid),
    ]
    with _patched_module_attrs(replacements):
        return detect_config.build_detected_config(
            device,
            rootless_podman_users=rootless_podman_users,
        )


def command_bootstrap(args: argparse.Namespace) -> int:
    from homelab_ha_discovery.installer import app_install

    with _patched_module_attrs([(app_install, "run_command", run_command)]):
        return app_install.command_bootstrap(args)


def _call_systemd_manager(command_name: str, args: argparse.Namespace) -> int:
    from homelab_ha_discovery.installer import systemd_manager

    with _patched_module_attrs([(systemd_manager, "run_command", run_command)]):
        command = getattr(systemd_manager, command_name)
        return command(args)


def command_install(args: argparse.Namespace) -> int:
    return _call_systemd_manager("command_install", args)


def command_enable(args: argparse.Namespace) -> int:
    return _call_systemd_manager("command_enable", args)


def command_stop(args: argparse.Namespace) -> int:
    return _call_systemd_manager("command_stop", args)


def command_restart(args: argparse.Namespace) -> int:
    return _call_systemd_manager("command_restart", args)


def command_disable(args: argparse.Namespace) -> int:
    return _call_systemd_manager("command_disable", args)


def command_uninstall(args: argparse.Namespace) -> int:
    return _call_systemd_manager("command_uninstall", args)


def command_logs(args: argparse.Namespace) -> int:
    return _call_systemd_manager("command_logs", args)


def command_status(args: argparse.Namespace) -> int:
    from homelab_ha_discovery.installer.systemd_manager import command_status

    return command_status(args, Path(__file__).resolve())


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed

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
    bootstrap_parser.add_argument(
        "--rootless-podman-user",
        action="append",
        default=[],
        metavar="USER",
        help=(
            "Detect rootless Podman containers for USER. Repeat for multiple "
            "users."
        ),
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
    detect_parser.add_argument(
        "--rootless-podman-user",
        action="append",
        default=[],
        metavar="USER",
        help=(
            "Detect rootless Podman containers for USER. Repeat for multiple "
            "users."
        ),
    )
    detect_parser.set_defaults(func=command_detect)

    install_parser = subparsers.add_parser(
        "install",
        help="Generate systemd service files from host-metrics.json.",
    )
    add_common_options(install_parser)
    install_cleanup_group = install_parser.add_mutually_exclusive_group()
    install_cleanup_group.add_argument(
        "--clean-existing-units",
        action="store_true",
        help=(
            "Remove existing homelab-ha-discovery-*.service files before "
            "writing regenerated units."
        ),
    )
    install_cleanup_group.add_argument(
        "--no-clean-existing-units",
        action="store_true",
        help="Keep existing homelab-ha-discovery-*.service files without prompting.",
    )
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

    stop_parser = subparsers.add_parser(
        "stop",
        help="Stop generated systemd services.",
    )
    add_common_options(stop_parser)
    stop_parser.set_defaults(func=command_stop)

    restart_parser = subparsers.add_parser(
        "restart",
        help="Restart generated systemd services.",
    )
    add_common_options(restart_parser)
    restart_parser.set_defaults(func=command_restart)

    disable_parser = subparsers.add_parser(
        "disable",
        help="Disable generated systemd services.",
    )
    add_common_options(disable_parser)
    disable_parser.add_argument(
        "--now",
        action="store_true",
        help="Stop the generated services immediately after disabling them.",
    )
    disable_parser.set_defaults(func=command_disable)

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        help="Stop, disable, and remove generated systemd service files.",
    )
    add_common_options(uninstall_parser)
    uninstall_parser.set_defaults(func=command_uninstall)

    logs_parser = subparsers.add_parser(
        "logs",
        help="Show journal logs for generated systemd services.",
    )
    add_common_options(logs_parser)
    logs_parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow logs.",
    )
    logs_parser.add_argument(
        "--lines",
        type=positive_int,
        help="Show the most recent N journal lines.",
    )
    logs_parser.add_argument(
        "--since",
        help='Show logs since a journalctl time expression, such as "1 hour ago".',
    )
    logs_parser.set_defaults(func=command_logs)

    status_parser = subparsers.add_parser(
        "status",
        help="Print generated unit names and useful service commands.",
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
