"""Read Podman container metrics from the Podman CLI."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
import subprocess
import time
from typing import Any


LabelSelectors = tuple[tuple[str, str | None], ...]
PodmanMetricValue = str | float | int
PodmanMetricPayload = dict[str, PodmanMetricValue]
BITS_PER_MEGABIT = 1000_000.0
BYTES_PER_MEGABYTE = 1000_000.0
METRIC_DECIMAL_PLACES = 3
PODMAN_COMPONENT_RE = re.compile(r"[^a-z0-9_]+")
PODMAN_COMPONENT_LABEL = "homelab-ha-discovery.component"
PODMAN_ENABLED_LABEL = "homelab-ha-discovery.enabled"
UNAVAILABLE_VALUES = {"", "--", "<nil>", "nil", "none", "null"}


@dataclass(frozen=True)
class PodmanContainerInfo:
    container_id: str
    name: str
    component: str
    state: str
    health: str
    restart_count: int
    labels: dict[str, str]


@dataclass(frozen=True)
class PodmanContainerStats:
    cpu_usage_percent: float
    memory_usage_bytes: float
    memory_limit_bytes: float
    memory_usage_percent: float
    network_rx_bytes: float
    network_tx_bytes: float


@dataclass(frozen=True)
class PodmanContainerSample:
    containers: dict[str, PodmanContainerInfo]
    stats: dict[str, PodmanContainerStats]
    timestamp: float


@dataclass(frozen=True)
class PodmanContainerMetrics:
    component: str
    name: str
    payload: PodmanMetricPayload


ZERO_STATS = PodmanContainerStats(
    cpu_usage_percent=0.0,
    memory_usage_bytes=0.0,
    memory_limit_bytes=0.0,
    memory_usage_percent=0.0,
    network_rx_bytes=0.0,
    network_tx_bytes=0.0,
)


def parse_label_selector(selector: str) -> tuple[str, str | None]:
    text = selector.strip()
    if not text:
        raise ValueError("label selector is required")
    if "=" not in text:
        if text == PODMAN_ENABLED_LABEL:
            return text, "true"
        return text, None

    key, value = text.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"invalid label selector: {selector!r}")
    value = value.strip()
    if key == PODMAN_ENABLED_LABEL:
        if value.lower() != "true":
            raise ValueError(f"{PODMAN_ENABLED_LABEL} must be true when included")
        value = "true"
    return key, value


def labels_match_selectors(
    labels: dict[str, str],
    selectors: LabelSelectors,
) -> bool:
    for key, expected_value in selectors:
        if key not in labels:
            return False
        if key == PODMAN_ENABLED_LABEL:
            if labels[key].strip().lower() != "true":
                return False
            continue
        if expected_value is not None and labels[key] != expected_value:
            return False
    return True


def podman_component_from_name(name: str) -> str:
    component = PODMAN_COMPONENT_RE.sub("_", name.strip().lower()).strip("_")
    if not component:
        raise ValueError(f"could not derive Podman component from {name!r}")
    return component


def podman_component_from_container(
    name: str,
    labels: dict[str, str],
) -> str:
    override = labels.get(PODMAN_COMPONENT_LABEL, "").strip()
    return podman_component_from_name(override or name)


def value_is_unavailable(value: object) -> bool:
    return str(value).strip().lower() in UNAVAILABLE_VALUES


def parse_percent(value: object, field_name: str) -> float:
    if value_is_unavailable(value):
        return 0.0
    text = str(value).strip()
    if text.endswith("%"):
        text = text[:-1]
    try:
        parsed = float(text)
    except ValueError as exc:
        raise ValueError(f"invalid Podman {field_name}: {value!r}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"invalid Podman {field_name}: {value!r}")
    return round(parsed, METRIC_DECIMAL_PLACES)


def parse_byte_quantity(value: object) -> float:
    if value_is_unavailable(value):
        return 0.0
    text = str(value).strip().replace(" ", "")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)", text)
    if not match:
        raise ValueError(f"invalid Podman byte quantity: {value!r}")

    number_text, unit = match.groups()
    factors = {
        "B": 1.0,
        "kB": 1000.0,
        "KB": 1000.0,
        "MB": 1000.0**2,
        "GB": 1000.0**3,
        "TB": 1000.0**4,
        "PB": 1000.0**5,
        "KiB": 1024.0,
        "MiB": 1024.0**2,
        "GiB": 1024.0**3,
        "TiB": 1024.0**4,
        "PiB": 1024.0**5,
    }
    factor = factors.get(unit)
    if factor is None:
        raise ValueError(f"unsupported Podman byte unit in {value!r}")

    return float(number_text) * factor


def parse_pair(value: object, field_name: str) -> tuple[float, float]:
    if value_is_unavailable(value):
        return 0.0, 0.0
    parts = [part.strip() for part in str(value).split("/", 1)]
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"invalid Podman {field_name}: {value!r}")
    if all(value_is_unavailable(part) for part in parts):
        return 0.0, 0.0
    return parse_byte_quantity(parts[0]), parse_byte_quantity(parts[1])


def container_name_from_inspect(item: dict[str, Any]) -> str:
    name = item.get("Name")
    if isinstance(name, str) and name.strip("/"):
        return name.strip("/")

    config = item.get("Config")
    if isinstance(config, dict):
        hostname = config.get("Hostname")
        if isinstance(hostname, str) and hostname.strip():
            return hostname.strip()

    container_id = str(item.get("Id", item.get("ID", ""))).strip()
    if container_id:
        return container_id[:12]
    raise ValueError("Podman inspect item is missing a container name")


def labels_from_inspect(item: dict[str, Any]) -> dict[str, str]:
    config = item.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        labels = item.get("Labels")
    if not isinstance(labels, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in labels.items()
        if value is not None
    }


def health_from_state(state: dict[str, Any]) -> str:
    for key in ("Health", "Healthcheck"):
        health_data = state.get(key)
        if not isinstance(health_data, dict):
            continue
        status = health_data.get("Status")
        if isinstance(status, str) and status.strip():
            return status.strip()
    return "none"


def parse_podman_inspect(
    inspect_output: str,
    include_label_selectors: LabelSelectors = (),
) -> dict[str, PodmanContainerInfo]:
    try:
        items = json.loads(inspect_output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Podman inspect JSON: {exc}") from exc
    if not isinstance(items, list):
        raise ValueError("Podman inspect JSON must be a list")

    containers: dict[str, PodmanContainerInfo] = {}
    components: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Podman inspect item must be an object")

        container_id = str(item.get("Id", item.get("ID", ""))).strip()
        if not container_id:
            raise ValueError("Podman inspect item is missing Id")

        labels = labels_from_inspect(item)
        if not labels_match_selectors(labels, include_label_selectors):
            continue

        state = item.get("State")
        if not isinstance(state, dict):
            state = {}
        status = str(state.get("Status") or "unknown")
        health = health_from_state(state)

        try:
            restart_count = int(item.get("RestartCount") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid Podman restart count for {container_id[:12]}"
            ) from exc

        name = container_name_from_inspect(item)
        component = podman_component_from_container(name, labels)
        previous_container = components.get(component)
        if previous_container is not None:
            raise ValueError(
                "multiple Podman containers resolve to component "
                f"{component!r}: {previous_container}, {name}"
            )
        components[component] = name
        containers[container_id] = PodmanContainerInfo(
            container_id=container_id,
            name=name,
            component=component,
            state=status,
            health=health,
            restart_count=restart_count,
            labels=labels,
        )

    return containers


def stats_key_from_item(item: dict[str, Any]) -> str:
    for key in ("id", "ID", "ContainerID", "Container", "name", "Name"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    raise ValueError(f"Podman stats item is missing ID: {item!r}")


def parse_podman_stats_item(item: dict[str, Any]) -> tuple[str, PodmanContainerStats]:
    container_key = stats_key_from_item(item)
    memory_usage, memory_limit = parse_pair(
        item.get("mem_usage", item.get("MemUsage", "")),
        "mem_usage",
    )
    network_rx, network_tx = parse_pair(
        item.get("netio", item.get("NetIO", "")),
        "netio",
    )
    return container_key, PodmanContainerStats(
        cpu_usage_percent=parse_percent(
            item.get("cpu_percent", item.get("CPUPerc", item.get("CPU", ""))),
            "cpu_percent",
        ),
        memory_usage_bytes=memory_usage,
        memory_limit_bytes=memory_limit,
        memory_usage_percent=parse_percent(
            item.get("mem_percent", item.get("MemPerc", "")),
            "mem_percent",
        ),
        network_rx_bytes=network_rx,
        network_tx_bytes=network_tx,
    )


def parse_podman_stats_line(line: str) -> tuple[str, PodmanContainerStats]:
    try:
        item = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Podman stats JSON line: {line!r}") from exc
    if not isinstance(item, dict):
        raise ValueError(f"Podman stats line must be an object: {line!r}")
    return parse_podman_stats_item(item)


def resolve_stats_container_id(
    stats_key: str,
    containers: dict[str, PodmanContainerInfo],
) -> str | None:
    if stats_key in containers:
        return stats_key

    prefix_matches = [
        container_id
        for container_id in containers
        if container_id.startswith(stats_key)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    name_matches = [
        container_id
        for container_id, container in containers.items()
        if container.name == stats_key or container.name == stats_key.strip("/")
    ]
    if len(name_matches) == 1:
        return name_matches[0]

    return None


def iter_podman_stats_items(stats_output: str) -> list[dict[str, Any]]:
    text = stats_output.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        if not all(isinstance(item, dict) for item in parsed):
            raise ValueError("Podman stats JSON list must contain objects")
        return parsed
    if isinstance(parsed, dict):
        return [parsed]

    items = []
    for line in stats_output.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid Podman stats JSON line: {line!r}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"Podman stats line must be an object: {line!r}")
        items.append(item)
    return items


def parse_podman_stats(
    stats_output: str,
    containers: dict[str, PodmanContainerInfo],
) -> dict[str, PodmanContainerStats]:
    stats: dict[str, PodmanContainerStats] = {}
    for item in iter_podman_stats_items(stats_output):
        stats_key, parsed_stats = parse_podman_stats_item(item)
        container_id = resolve_stats_container_id(stats_key, containers)
        if container_id is not None:
            stats[container_id] = parsed_stats
    return stats


def run_podman_command(
    command: list[str],
    timeout: float = 10.0,
) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout


def run_podman_container_ids(
    podman_command: str = "podman",
    include_all: bool = False,
) -> list[str]:
    command = [podman_command, "ps", "--no-trunc", "--quiet"]
    if include_all:
        command.append("--all")
    output = run_podman_command(command)
    return [line.strip() for line in output.splitlines() if line.strip()]


def run_podman_inspect(
    container_ids: list[str],
    podman_command: str = "podman",
) -> str:
    if not container_ids:
        return "[]"
    return run_podman_command(
        [podman_command, "container", "inspect", *container_ids]
    )


def run_podman_stats(
    container_ids: list[str],
    podman_command: str = "podman",
    include_all: bool = False,
) -> str:
    if not container_ids:
        return ""
    command = [
        podman_command,
        "stats",
        "--no-stream",
        "--no-trunc",
        "--format=json",
    ]
    if include_all:
        command.append("--all")
    command.extend(container_ids)
    return run_podman_command(command)


def read_podman_container_sample(
    podman_command: str = "podman",
    include_all: bool = False,
    include_label_selectors: LabelSelectors = (),
) -> PodmanContainerSample:
    container_ids = run_podman_container_ids(
        podman_command=podman_command,
        include_all=include_all,
    )
    containers = parse_podman_inspect(
        run_podman_inspect(container_ids, podman_command=podman_command),
        include_label_selectors=include_label_selectors,
    )
    filtered_container_ids = list(containers)
    stats = parse_podman_stats(
        run_podman_stats(
            filtered_container_ids,
            podman_command=podman_command,
            include_all=include_all,
        ),
        containers,
    )
    return PodmanContainerSample(
        containers=containers,
        stats=stats,
        timestamp=time.monotonic(),
    )


def stats_for_container(
    sample: PodmanContainerSample,
    container: PodmanContainerInfo,
) -> PodmanContainerStats:
    stats = sample.stats.get(container.container_id)
    if stats is not None:
        return stats
    if container.state != "running":
        return ZERO_STATS
    raise ValueError(f"Podman stats missing for running container {container.name!r}")


def speed_from_counter_delta(
    previous_bytes: float,
    current_bytes: float,
    elapsed_seconds: float,
) -> float:
    delta = current_bytes - previous_bytes
    if delta < 0:
        return 0.0
    return round(
        delta * 8 / elapsed_seconds / BITS_PER_MEGABIT,
        METRIC_DECIMAL_PLACES,
    )


def calculate_podman_container_metrics(
    previous: PodmanContainerSample,
    current: PodmanContainerSample,
) -> tuple[list[PodmanContainerMetrics], list[str]]:
    elapsed_seconds = current.timestamp - previous.timestamp
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError("elapsed time between Podman samples must be greater than 0")

    metrics: list[PodmanContainerMetrics] = []
    skipped_components: list[str] = []
    for container in sorted(
        current.containers.values(),
        key=lambda item: item.component,
    ):
        previous_stats = previous.stats.get(container.container_id)
        if previous_stats is None:
            if container.state == "running":
                skipped_components.append(container.component)
                continue
            previous_stats = ZERO_STATS

        current_stats = stats_for_container(current, container)
        metrics.append(
            PodmanContainerMetrics(
                component=container.component,
                name=container.name,
                payload={
                    "State": container.state,
                    "Health": container.health,
                    "Restart Count": container.restart_count,
                    "CPU Usage": current_stats.cpu_usage_percent,
                    "Memory Usage MB": round(
                        current_stats.memory_usage_bytes / BYTES_PER_MEGABYTE,
                        METRIC_DECIMAL_PLACES,
                    ),
                    "Memory Limit MB": round(
                        current_stats.memory_limit_bytes / BYTES_PER_MEGABYTE,
                        METRIC_DECIMAL_PLACES,
                    ),
                    "Memory Usage Percent": current_stats.memory_usage_percent,
                    "Download Speed": speed_from_counter_delta(
                        previous_stats.network_rx_bytes,
                        current_stats.network_rx_bytes,
                        elapsed_seconds,
                    ),
                    "Upload Speed": speed_from_counter_delta(
                        previous_stats.network_tx_bytes,
                        current_stats.network_tx_bytes,
                        elapsed_seconds,
                    ),
                },
            )
        )

    return metrics, skipped_components
