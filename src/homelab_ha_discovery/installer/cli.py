"""Grouped installer CLI for homelab-ha-discovery."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import subprocess
import sys

from homelab_ha_discovery.installer import app_install, systemd_manager
from homelab_ha_discovery.installer.config_io import (
    DEFAULT_APP_DIR,
    DEFAULT_CONFIG_DIR,
    DEFAULT_SYSTEMD_DIR,
    build_paths,
    ensure_config_dir,
    ensure_mqtt_env,
    load_config,
    write_detected_config,
)
from homelab_ha_discovery.installer.systemd_units import build_unit_specs


DEFAULT_BIN_DIR = Path("/usr/local/bin")


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
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


def hhdctl_wrapper_text(paths) -> str:
    script_path = (
        paths.app_dir
        / "src"
        / "homelab_ha_discovery"
        / "scripts"
        / "hhdctl.py"
    )
    python_path = paths.app_dir / ".venv" / "bin" / "python"
    return "\n".join(
        (
            "#!/bin/sh",
            "exec "
            f"{shlex.quote(str(python_path))} "
            f"{shlex.quote(str(script_path))} \"$@\"",
            "",
        )
    )


def install_hhdctl_wrapper(paths, bin_dir: Path, dry_run: bool) -> None:
    wrapper_path = bin_dir / "hhdctl"
    wrapper_text = hhdctl_wrapper_text(paths)
    if dry_run:
        print(f"DRY RUN: would write hhdctl command wrapper {wrapper_path}")
        return

    if wrapper_path.exists():
        try:
            existing_text = wrapper_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            existing_text = ""
        if existing_text == wrapper_text:
            print(f"hhdctl command wrapper already current: {wrapper_path}")
            return
        print(
            f"Keeping existing hhdctl command wrapper: {wrapper_path}. "
            "Update it manually if it should point at this install.",
            file=sys.stderr,
        )
        return

    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(wrapper_text, encoding="utf-8")
    wrapper_path.chmod(0o755)
    print(f"Wrote hhdctl command wrapper: {wrapper_path}")


def command_app_install(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        if args.install_system_packages:
            app_install.install_system_packages(args.dry_run)
        app_install.prepare_app_dir(paths, args.force_copy, args.dry_run)
        app_install.create_virtualenv_and_install_requirements(paths, args.dry_run)
        install_hhdctl_wrapper(paths, args.bin_dir, args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_app_install_system_packages(args: argparse.Namespace) -> int:
    try:
        app_install.install_system_packages(args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_config_init_mqtt_env(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        ensure_config_dir(paths, args.dry_run)
        ensure_mqtt_env(paths, args.dry_run)
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_config_detect(args: argparse.Namespace) -> int:
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
            include_podman=args.include_podman,
            podman_socket=args.podman_socket,
            rootless_podman_uids=args.rootless_podman_uid,
            auto_discover_rootless_podman=args.auto_discover_rootless_podman,
        )
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_systemd_render(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    if args.dry_run and not paths.config_path.exists():
        print(
            f"DRY RUN: config not found: {paths.config_path}; "
            "would render systemd units after config exists"
        )
        return 0
    return systemd_manager.command_install(args)


def command_systemd_status(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = build_unit_specs(paths, load_config(paths))
    except (OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not units:
        print(f"No enabled services in {paths.config_path}")
        return 0

    configured_unit_names = [unit.name for unit in units]
    print(f"Config: {paths.config_path}")
    print("Generated unit names:")
    for unit_name in configured_unit_names:
        print(f"  {unit_name}")
    print("Useful commands:")
    quoted_units = " ".join(shlex.quote(name) for name in configured_unit_names)
    print("  systemctl status " + quoted_units)
    print("  sudo hhdctl systemd logs --follow")
    print("  sudo hhdctl systemd restart")
    print("  sudo hhdctl systemd stop")
    print("  sudo hhdctl systemd disable --now")
    print("  sudo hhdctl systemd uninstall")
    return 0


def add_config_detect_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ha-device-id",
        dest="device",
        required=True,
        help="Stable Home Assistant/MQTT device identity.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing host-metrics.json.",
    )
    parser.add_argument(
        "--include-podman",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include Podman container service templates in detected config.",
    )
    parser.add_argument(
        "--podman-socket",
        help=(
            "Podman service socket URI or path to record in detected Podman "
            "service entries."
        ),
    )
    parser.add_argument(
        "--rootless-podman-user",
        action="append",
        default=[],
        metavar="USER",
        help=(
            "Detect rootless Podman containers for USER. Repeat for multiple "
            "users."
        ),
    )
    parser.add_argument(
        "--rootless-podman-uid",
        action="append",
        default=[],
        type=non_negative_int,
        metavar="UID",
        help="Detect rootless Podman containers for UID. Repeat for multiple UIDs.",
    )
    parser.add_argument(
        "--auto-discover-rootless-podman",
        action="store_true",
        help="Discover rootless Podman users from /run/user Podman sockets.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hhdctl", description=__doc__)
    subparsers = parser.add_subparsers(dest="group", required=True)

    app_parser = subparsers.add_parser("app", help="Manage the application copy.")
    app_subparsers = app_parser.add_subparsers(dest="command", required=True)

    app_install_parser = app_subparsers.add_parser(
        "install",
        help="Copy the checkout and create the managed virtualenv.",
    )
    add_common_options(app_install_parser)
    app_install_parser.add_argument(
        "--force-copy",
        action="store_true",
        help=f"Replace {DEFAULT_APP_DIR} if it already exists.",
    )
    app_install_parser.add_argument(
        "--install-system-packages",
        action="store_true",
        help="Install Debian packages with apt-get before installing the app.",
    )
    app_install_parser.add_argument(
        "--bin-dir",
        type=Path,
        default=DEFAULT_BIN_DIR,
        help=f"Directory for the hhdctl command wrapper. Default: {DEFAULT_BIN_DIR}",
    )
    app_install_parser.set_defaults(func=command_app_install)

    packages_parser = app_subparsers.add_parser(
        "install-system-packages",
        help="Install Debian packages required by host publishers.",
    )
    packages_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned apt-get commands without changing the system.",
    )
    packages_parser.set_defaults(func=command_app_install_system_packages)

    config_parser = subparsers.add_parser("config", help="Manage installer config.")
    config_subparsers = config_parser.add_subparsers(dest="command", required=True)

    mqtt_env_parser = config_subparsers.add_parser(
        "init-mqtt-env",
        help="Create mqtt.env if it does not already exist.",
    )
    add_common_options(mqtt_env_parser)
    mqtt_env_parser.set_defaults(func=command_config_init_mqtt_env)

    detect_parser = config_subparsers.add_parser(
        "detect",
        help="Detect local host metrics and write host-metrics.json.",
    )
    add_common_options(detect_parser)
    add_config_detect_options(detect_parser)
    detect_parser.set_defaults(func=command_config_detect)

    systemd_parser = subparsers.add_parser(
        "systemd",
        help="Render and control generated systemd units.",
    )
    systemd_subparsers = systemd_parser.add_subparsers(dest="command", required=True)

    render_parser = systemd_subparsers.add_parser(
        "render",
        help="Generate systemd service files from host-metrics.json.",
    )
    add_common_options(render_parser)
    render_cleanup_group = render_parser.add_mutually_exclusive_group()
    render_cleanup_group.add_argument(
        "--clean-existing-units",
        action="store_true",
        help=(
            "Remove existing homelab-ha-discovery-*.service files before "
            "writing regenerated units."
        ),
    )
    render_cleanup_group.add_argument(
        "--no-clean-existing-units",
        action="store_true",
        help="Keep existing homelab-ha-discovery-*.service files without prompting.",
    )
    render_parser.set_defaults(func=command_systemd_render)

    enable_parser = systemd_subparsers.add_parser(
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
    enable_parser.set_defaults(func=systemd_manager.command_enable)

    disable_parser = systemd_subparsers.add_parser(
        "disable",
        help="Disable generated systemd services.",
    )
    add_common_options(disable_parser)
    disable_parser.add_argument(
        "--now",
        action="store_true",
        help="Stop the generated services immediately after disabling them.",
    )
    disable_parser.set_defaults(func=systemd_manager.command_disable)

    restart_parser = systemd_subparsers.add_parser(
        "restart",
        help="Restart generated systemd services.",
    )
    add_common_options(restart_parser)
    restart_parser.set_defaults(func=systemd_manager.command_restart)

    stop_parser = systemd_subparsers.add_parser(
        "stop",
        help="Stop generated systemd services.",
    )
    add_common_options(stop_parser)
    stop_parser.set_defaults(func=systemd_manager.command_stop)

    status_parser = systemd_subparsers.add_parser(
        "status",
        help="Print generated unit names and useful service commands.",
    )
    add_common_options(status_parser)
    status_parser.set_defaults(func=command_systemd_status)

    logs_parser = systemd_subparsers.add_parser(
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
    logs_parser.set_defaults(func=systemd_manager.command_logs)

    uninstall_parser = systemd_subparsers.add_parser(
        "uninstall",
        help="Stop, disable, and remove generated systemd service files.",
    )
    add_common_options(uninstall_parser)
    uninstall_parser.set_defaults(func=systemd_manager.command_uninstall)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
