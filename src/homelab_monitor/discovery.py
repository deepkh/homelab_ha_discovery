"""Home Assistant MQTT naming helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_TOPIC_PREFIX = "homelab-mqtt-monitor"


def mqtt_topic_prefix() -> str:
    return os.environ.get("HA_MQTT_TOPIC_PREFIX", DEFAULT_TOPIC_PREFIX).strip("/")


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
        return f"{self.host}_{self.component}_{self.metric}"

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
    return config
