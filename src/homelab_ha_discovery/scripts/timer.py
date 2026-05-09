"""Timer loop helpers for publisher scripts."""

from __future__ import annotations

from collections.abc import Callable
import math
import sys
import time


Publish = Callable[[], int]


def validate_timer_seconds(timer: float | None, argument: str) -> bool:
    """Return whether a timer argument is unset or a finite positive value."""
    if timer is not None and (not math.isfinite(timer) or timer <= 0):
        print(
            f"Error: {argument} must be a finite value greater than 0",
            file=sys.stderr,
        )
        return False
    return True


def run_publish_timer(timer: float | None, publish: Publish) -> int:
    """Run one publish attempt, or repeat it every timer seconds."""
    if not validate_timer_seconds(timer, "--timer"):
        return 1

    try:
        while True:
            try:
                result = publish()
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            if result != 0:
                return result
            if timer is None:
                return 0
            time.sleep(timer)
    except KeyboardInterrupt:
        return 0
