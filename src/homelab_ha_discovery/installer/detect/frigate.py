"""Frigate detection helpers for generated host metrics config."""

from __future__ import annotations

import urllib.error
import urllib.request

from homelab_ha_discovery.installer.config_io import FRIGATE_DETECT_TIMEOUT_SECONDS


def http_url_reachable(
    url: str,
    timeout: float = FRIGATE_DETECT_TIMEOUT_SECONDS,
) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            return 200 <= status < 300
    except (OSError, urllib.error.URLError):
        return False
