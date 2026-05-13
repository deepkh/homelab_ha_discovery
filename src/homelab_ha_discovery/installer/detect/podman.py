"""Podman detection helpers for generated host metrics config."""

from __future__ import annotations

import pwd
import re
import shutil
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

def user_uid(user: str) -> int | None:
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        return None

def podman_ps_command(
    podman_command: str,
    rootless_user: str | None = None,
    rootless_uid: int | None = None,
) -> list[str]:
    command = [podman_command, "ps", "--quiet"]
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
        *command,
    ]

def detect_podman_has_running_containers(
    podman_command: str,
    rootless_user: str | None = None,
    rootless_uid: int | None = None,
) -> bool:
    return command_has_output(
        podman_ps_command(
            podman_command,
            rootless_user=rootless_user,
            rootless_uid=rootless_uid,
        )
    )

def detected_podman_service_entries(
    rootless_podman_users: list[str] | tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    podman_command = shutil.which("podman") or "podman"
    podman_exists = command_exists("podman")
    podman_missing = [] if podman_exists else ["podman"]
    root_enabled = (
        podman_exists
        and detect_podman_has_running_containers(podman_command)
    )
    root_note = (
        "publishes running root Podman containers"
        if root_enabled
        else "disabled template; enable after root Podman containers are running"
    )
    services = [
        service_entry(
            "podman_containers",
            root_enabled,
            scope="root",
            include_label=DEFAULT_CONTAINER_INCLUDE_LABEL,
            podman_command=podman_command if podman_exists else "podman",
            expire_after=None,
            missing_requirements=podman_missing,
            note=root_note,
        )
    ]

    for user in unique_rootless_podman_users(tuple(rootless_podman_users)):
        uid = user_uid(user)
        missing_requirements = list(podman_missing)
        if uid is None:
            missing_requirements.append(f"user:{user}")
        if not command_exists("runuser"):
            missing_requirements.append("runuser")

        enabled = (
            not missing_requirements
            and uid is not None
            and detect_podman_has_running_containers(
                podman_command,
                rootless_user=user,
                rootless_uid=uid,
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
        if uid is not None:
            values["rootless_uid"] = uid
        services.append(
            service_entry(
                "podman_containers",
                enabled,
                **values,
            )
        )

    return services
