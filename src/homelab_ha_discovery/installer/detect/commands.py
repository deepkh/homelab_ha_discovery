"""Command probing helpers used by installer detection."""

from __future__ import annotations

import shutil
import subprocess


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None

def command_output(command: list[str], timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()

def command_has_output(command: list[str], timeout: float = 5.0) -> bool:
    return bool(command_output(command, timeout=timeout))
