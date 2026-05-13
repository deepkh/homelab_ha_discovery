"""Application copy and bootstrap helpers for the systemd installer."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

from homelab_ha_discovery.installer.config_io import (
    RuntimePaths,
    build_paths,
    ensure_config_dir,
    ensure_mqtt_env,
    write_detected_config,
)
from homelab_ha_discovery.installer.systemd_manager import run_command


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

def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]

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


def command_bootstrap(args) -> int:
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
            rootless_podman_users=args.rootless_podman_user,
            force=args.force_config,
            dry_run=args.dry_run,
            force_option="--force-config",
            include_podman=getattr(args, "include_podman", True),
            podman_socket=getattr(args, "podman_socket", None),
            rootless_podman_uids=getattr(args, "rootless_podman_uid", ()),
            auto_discover_rootless_podman=getattr(
                args,
                "auto_discover_rootless_podman",
                False,
            ),
        )
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
