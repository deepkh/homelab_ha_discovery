"""Home Assistant MQTT naming helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import sys


DEFAULT_TOPIC_PREFIX = "homelab-ha-discovery"
DEFAULT_OBJECT_ID_PREFIX = "homelab_ha_discovery"
DISCOVERY_EXPIRE_AFTER_TIMER_MULTIPLIER = 3.0


def mqtt_topic_prefix() -> str:
    return os.environ.get("HA_MQTT_TOPIC_PREFIX", DEFAULT_TOPIC_PREFIX).strip("/")


def validate_expire_after_seconds(
    expire_after: float | None,
    argument: str = "--expire-after",
) -> bool:
    """Return whether an expire_after argument is unset or finite non-negative."""
    if expire_after is not None and (
        not math.isfinite(expire_after) or expire_after < 0
    ):
        print(
            f"Error: {argument} must be a finite value greater than or equal to 0",
            file=sys.stderr,
        )
        return False
    return True


def effective_expire_after(
    expire_after: float | None,
    timer: float | None,
) -> float | None:
    """Return the discovery expiry to write, or None when expiry is disabled."""
    if expire_after == 0:
        return None
    if expire_after is not None:
        return expire_after
    if timer is None:
        return None
    return timer * DISCOVERY_EXPIRE_AFTER_TIMER_MULTIPLIER


def discovery_expire_after_config_value(expire_after: float | None) -> int | None:
    """Return the integer Home Assistant expire_after value, or None to omit it."""
    if expire_after is None or expire_after == 0:
        return None
    if not math.isfinite(expire_after) or expire_after < 0:
        raise ValueError(
            "expire_after must be a finite value greater than or equal to 0"
        )
    return int(math.ceil(expire_after))


@dataclass(frozen=True)
class MetricIdentity:
    host: str
    component: str
    metric: str
    state_topic_override: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("host", self.host),
            ("component", self.component),
            ("metric", self.metric),
        ):
            if not value:
                raise ValueError(f"{field_name} is required")

    @property
    def object_id(self) -> str:
        return f"{DEFAULT_OBJECT_ID_PREFIX}_{self.host}_{self.component}_{self.metric}"

    @property
    def unique_id(self) -> str:
        return self.object_id

    @property
    def state_topic(self) -> str:
        if self.state_topic_override:
            return self.state_topic_override
        return f"{mqtt_topic_prefix()}/{self.host}/{self.component}/{self.metric}/state"

    @property
    def discovery_topic(self) -> str:
        return f"homeassistant/sensor/{self.object_id}/config"

    @property
    def device_identifier(self) -> str:
        return f"{mqtt_topic_prefix()}_{self.host}"

    @property
    def device_name(self) -> str:
        return self.host


def sensor_discovery_config(
    identity: MetricIdentity,
    name: str,
    unit_of_measurement: str | None = None,
    device_class: str | None = None,
    state_class: str | None = None,
    value_template: str | None = None,
    expire_after: float | None = None,
) -> dict[str, object]:
    config: dict[str, object] = {
        "name": name,
        "unique_id": identity.unique_id,
        "state_topic": identity.state_topic,
        "device": {
            "identifiers": [identity.device_identifier],
            "name": identity.device_name,
        },
    }
    if unit_of_measurement:
        config["unit_of_measurement"] = unit_of_measurement
    if device_class:
        config["device_class"] = device_class
    if state_class:
        config["state_class"] = state_class
    if value_template:
        config["value_template"] = value_template
    expire_after_config = discovery_expire_after_config_value(expire_after)
    if expire_after_config is not None:
        config["expire_after"] = expire_after_config
    return config
