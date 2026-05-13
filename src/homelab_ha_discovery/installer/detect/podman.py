"""Podman detection helpers for generated host metrics config."""

from __future__ import annotations

import pwd
import re
import shutil
from pathlib import Path
from typing import Any

from homelab_ha_discovery.installer.config_io import (
    DEFAULT_CONTAINER_INCLUDE_LABEL,
    require_string,
    service_entry,
)
from homelab_ha_discovery.installer.detect.commands import (
    command_exists,
    command_has_output,
)


PODMAN_SCOPE_RE = re.compile(r"[^a-z0-9_]+")

def podman_scope_from_value(value: str) -> str:
    scope = PODMAN_SCOPE_RE.sub("_", value.strip().lower()).strip("_")
    if not scope:
        raise RuntimeError("podman scope is required")
    return scope

def unique_rootless_podman_users(values: list[str] | tuple[str, ...]) -> list[str]:
    users: list[str] = []
    for value in values:
        user = require_string(value, "rootless_podman_user")
        if user not in users:
            users.append(user)
    return users

def normalize_podman_socket(value: str | None) -> str | None:
    if value is None:
        return None
    socket = require_string(value, "podman_socket")
    if "://" in socket:
        return socket
    return f"unix://{socket}"

def user_uid(user: str) -> int | None:
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        return None

def user_from_uid(uid: int) -> str | None:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return None

def auto_discovered_rootless_podman_users() -> list[str]:
    users: list[str] = []
    run_user_dir = Path("/run/user")
    if not run_user_dir.exists():
        return users

    for podman_socket in sorted(run_user_dir.glob("*/podman/podman.sock")):
        try:
            uid = int(podman_socket.parents[1].name)
        except ValueError:
            continue
        user = user_from_uid(uid)
        if user is not None and user not in users:
            users.append(user)
    return users

def podman_ps_command(
    podman_command: str,
    rootless_user: str | None = None,
    rootless_uid: int | None = None,
    podman_socket: str | None = None,
) -> list[str]:
    command = [podman_command]
    normalized_socket = normalize_podman_socket(podman_socket)
    if normalized_socket is not None:
        command.extend(["--url", normalized_socket])
    command.extend(["ps", "--quiet"])
    if rootless_user is None:
        return command
    if rootless_uid is None:
        raise RuntimeError(
            f"uid for rootless Podman user is required: {rootless_user}"
        )
    return [
        "runuser",
        "-u",
        rootless_user,
        "--",
        "env",
        f"XDG_RUNTIME_DIR=/run/user/{rootless_uid}",
        *(
            [f"CONTAINER_HOST={normalized_socket}"]
            if normalized_socket is not None
            else []
        ),
        *command,
    ]

def detect_podman_has_running_containers(
    podman_command: str,
    rootless_user: str | None = None,
    rootless_uid: int | None = None,
    podman_socket: str | None = None,
) -> bool:
    return command_has_output(
        podman_ps_command(
            podman_command,
            rootless_user=rootless_user,
            rootless_uid=rootless_uid,
            podman_socket=podman_socket,
        )
    )

def _detect_podman_has_running_containers(
    podman_command: str,
    rootless_user: str | None = None,
    rootless_uid: int | None = None,
    podman_socket: str | None = None,
) -> bool:
    if podman_socket is None:
        return detect_podman_has_running_containers(
            podman_command,
            rootless_user=rootless_user,
            rootless_uid=rootless_uid,
        )
    return detect_podman_has_running_containers(
        podman_command,
        rootless_user=rootless_user,
        rootless_uid=rootless_uid,
        podman_socket=podman_socket,
    )

def detected_podman_service_entries(
    rootless_podman_users: list[str] | tuple[str, ...] = (),
    podman_socket: str | None = None,
    rootless_podman_uids: list[int] | tuple[int, ...] = (),
    auto_discover_rootless_podman: bool = False,
) -> list[dict[str, Any]]:
    podman_command = shutil.which("podman") or "podman"
    podman_exists = command_exists("podman")
    podman_missing = [] if podman_exists else ["podman"]
    normalized_socket = normalize_podman_socket(podman_socket)
    root_enabled = (
        podman_exists
        and _detect_podman_has_running_containers(
            podman_command,
            podman_socket=normalized_socket,
        )
    )
    root_note = (
        "publishes running root Podman containers"
        if root_enabled
        else "disabled template; enable after root Podman containers are running"
    )
    root_values: dict[str, Any] = {
        "scope": "root",
        "include_label": DEFAULT_CONTAINER_INCLUDE_LABEL,
        "podman_command": podman_command if podman_exists else "podman",
        "expire_after": None,
        "missing_requirements": podman_missing,
        "note": root_note,
    }
    if normalized_socket is not None:
        root_values["podman_socket"] = normalized_socket
    services = [service_entry("podman_containers", root_enabled, **root_values)]

    users = unique_rootless_podman_users(tuple(rootless_podman_users))
    if auto_discover_rootless_podman:
        for user in auto_discovered_rootless_podman_users():
            if user not in users:
                users.append(user)

    uid_only_values: list[int] = []
    for uid in rootless_podman_uids:
        user = user_from_uid(uid)
        if user is None:
            uid_only_values.append(uid)
        elif user not in users:
            users.append(user)

    for user in users:
        uid = user_uid(user)
        missing_requirements = list(podman_missing)
        if uid is None:
            missing_requirements.append(f"user:{user}")
        if not command_exists("runuser"):
            missing_requirements.append("runuser")

        enabled = (
            not missing_requirements
            and uid is not None
            and _detect_podman_has_running_containers(
                podman_command,
                rootless_user=user,
                rootless_uid=uid,
                podman_socket=normalized_socket,
            )
        )
        note = (
            f"publishes running rootless Podman containers for {user}"
            if enabled
            else (
                "disabled template; enable after rootless Podman containers "
                f"are running for {user}"
            )
        )
        values: dict[str, Any] = {
            "scope": podman_scope_from_value(user),
            "rootless_user": user,
            "include_label": DEFAULT_CONTAINER_INCLUDE_LABEL,
            "podman_command": podman_command if podman_exists else "podman",
            "expire_after": None,
            "missing_requirements": missing_requirements,
            "note": note,
        }
        if normalized_socket is not None:
            values["podman_socket"] = normalized_socket
        if uid is not None:
            values["rootless_uid"] = uid
        services.append(
            service_entry(
                "podman_containers",
                enabled,
                **values,
            )
        )

    for uid in uid_only_values:
        socket = normalized_socket or f"unix:///run/user/{uid}/podman/podman.sock"
        values = {
            "scope": f"uid_{uid}",
            "rootless_uid": uid,
            "include_label": DEFAULT_CONTAINER_INCLUDE_LABEL,
            "podman_command": podman_command if podman_exists else "podman",
            "podman_socket": socket,
            "expire_after": None,
            "missing_requirements": [*podman_missing, f"user_uid:{uid}"],
            "note": (
                "disabled template; rootless Podman UID could not be mapped to "
                "a local user"
            ),
        }
        services.append(service_entry("podman_containers", False, **values))

    return services
