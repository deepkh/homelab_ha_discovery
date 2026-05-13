"""systemd command orchestration for the Debian host installer."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
import subprocess
import sys

from homelab_ha_discovery.installer.config_io import (
    SERVICE_PREFIX,
    RuntimePaths,
    build_paths,
    load_config,
)
from homelab_ha_discovery.installer.systemd_units import (
    UnitSpec,
    build_unit_specs,
    write_units,
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

def existing_generated_unit_paths(systemd_dir: Path) -> list[Path]:
    if not systemd_dir.exists():
        return []
    return sorted(systemd_dir.glob(f"{SERVICE_PREFIX}-*.service"))

def unit_names(units: list[UnitSpec]) -> list[str]:
    return [unit.name for unit in units]

def unit_names_from_paths(unit_paths: list[Path]) -> list[str]:
    return [unit_path.name for unit_path in unit_paths]

def load_configured_units(paths: RuntimePaths) -> list[UnitSpec]:
    units = build_unit_specs(paths, load_config(paths))
    if not units:
        raise RuntimeError("no enabled services found in config")
    return units

def require_installed_unit_files(
    paths: RuntimePaths,
    units: list[UnitSpec],
    dry_run: bool,
) -> None:
    missing_units = [
        unit.name
        for unit in units
        if not unit.path(paths.systemd_dir).exists()
    ]
    if missing_units and not dry_run:
        raise RuntimeError(
            "systemd unit file(s) missing; run install first: "
            + ", ".join(missing_units)
        )

def remove_existing_generated_units(
    unit_paths: list[Path],
    dry_run: bool,
) -> None:
    for unit_path in unit_paths:
        if dry_run:
            print(f"DRY RUN: would remove existing systemd unit {unit_path}")
            continue
        unit_path.unlink()
        print(f"Removed existing systemd unit: {unit_path}")

def prompt_remove_existing_generated_units(unit_paths: list[Path]) -> bool:
    print("Existing homelab-ha-discovery systemd unit file(s) found:")
    for unit_path in unit_paths:
        print(f"  {unit_path}")
    answer = input(
        "Remove all existing homelab-ha-discovery-*.service files before "
        "writing regenerated units? [y/N] "
    )
    return answer.strip().lower() in {"y", "yes"}

def maybe_remove_existing_generated_units(
    paths: RuntimePaths,
    clean_existing_units: bool,
    no_clean_existing_units: bool,
    dry_run: bool,
) -> None:
    unit_paths = existing_generated_unit_paths(paths.systemd_dir)
    if not unit_paths:
        return

    if clean_existing_units:
        remove_existing_generated_units(unit_paths, dry_run)
        return

    if no_clean_existing_units:
        print("Keeping existing homelab-ha-discovery systemd unit files.")
        return

    if dry_run:
        print(
            "DRY RUN: would prompt to remove existing "
            f"{paths.systemd_dir}/{SERVICE_PREFIX}-*.service files"
        )
        for unit_path in unit_paths:
            print(f"  {unit_path}")
        return

    if not sys.stdin.isatty():
        print(
            "Existing homelab-ha-discovery systemd unit files were kept because "
            "stdin is not interactive. Pass --clean-existing-units to remove them.",
            file=sys.stderr,
        )
        return

    if prompt_remove_existing_generated_units(unit_paths):
        remove_existing_generated_units(unit_paths, dry_run=False)
    else:
        print("Keeping existing homelab-ha-discovery systemd unit files.")

def command_install(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = build_unit_specs(paths, load_config(paths))
        maybe_remove_existing_generated_units(
            paths,
            args.clean_existing_units,
            args.no_clean_existing_units,
            args.dry_run,
        )
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
        units = load_configured_units(paths)
        require_installed_unit_files(paths, units, args.dry_run)

        run_command(["systemctl", "daemon-reload"], args.dry_run)
        command = ["systemctl", "enable"]
        if args.now:
            command.append("--now")
        command.extend(unit_names(units))
        run_command(command, args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0

def command_stop(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = load_configured_units(paths)
        require_installed_unit_files(paths, units, args.dry_run)
        run_command(["systemctl", "stop", *unit_names(units)], args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0

def command_restart(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = load_configured_units(paths)
        require_installed_unit_files(paths, units, args.dry_run)
        run_command(["systemctl", "daemon-reload"], args.dry_run)
        run_command(["systemctl", "restart", *unit_names(units)], args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0

def command_disable(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = load_configured_units(paths)
        require_installed_unit_files(paths, units, args.dry_run)
        command = ["systemctl", "disable"]
        if args.now:
            command.append("--now")
        command.extend(unit_names(units))
        run_command(command, args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0

def command_uninstall(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        unit_paths = existing_generated_unit_paths(paths.systemd_dir)
        if not unit_paths:
            print(
                "No generated homelab-ha-discovery systemd unit files found in "
                f"{paths.systemd_dir}"
            )
            return 0

        names = unit_names_from_paths(unit_paths)
        run_command(["systemctl", "stop", *names], args.dry_run)
        run_command(["systemctl", "disable", *names], args.dry_run)
        remove_existing_generated_units(unit_paths, args.dry_run)
        run_command(["systemctl", "daemon-reload"], args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0

def command_logs(args: argparse.Namespace) -> int:
    paths = build_paths(args)
    try:
        units = load_configured_units(paths)
        command = ["journalctl"]
        if args.follow:
            command.append("-f")
        if args.lines is not None:
            command.extend(["-n", str(args.lines)])
        if args.since is not None:
            command.extend(["--since", args.since])
        for unit_name in unit_names(units):
            command.extend(["-u", unit_name])
        run_command(command, args.dry_run)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def command_status(args, script_path: Path) -> int:
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
    quoted_script_path = shlex.quote(str(script_path))
    print("  systemctl status " + quoted_units)
    print(f"  sudo python3 {quoted_script_path} logs --follow")
    print(f"  sudo python3 {quoted_script_path} restart")
    print(f"  sudo python3 {quoted_script_path} stop")
    print(f"  sudo python3 {quoted_script_path} disable --now")
    print(f"  sudo python3 {quoted_script_path} uninstall")
    return 0
