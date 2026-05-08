"""Read CPU usage from top."""

from __future__ import annotations

import os
import re
import subprocess


def run_top() -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    result = subprocess.run(
        ["top", "-bn1"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def parse_cpu_usage(top_output: str) -> float:
    for line in top_output.splitlines():
        if line.startswith("%Cpu") or line.startswith("Cpu(s)"):
            idle_match = re.search(r"(\d+(?:\.\d+)?)\s*id\b", line)
            if not idle_match:
                break

            idle_percent = float(idle_match.group(1))
            return round(max(0.0, min(100.0, 100.0 - idle_percent)), 1)

    raise ValueError("Could not find CPU idle percentage in top output")
