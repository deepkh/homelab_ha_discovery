"""Read Docker container metrics from the Docker CLI."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
import subprocess
import time
from typing import Any


LabelSelectors = tuple[tuple[str, str | None], ...]
DockerMetricValue = str | float | int
DockerMetricPayload = dict[str, DockerMetricValue]
BITS_PER_MEGABIT = 1000_000.0
BYTES_PER_MEGABYTE = 1000_000.0
METRIC_DECIMAL_PLACES = 3
DOCKER_COMPONENT_RE = re.compile(r"[^a-z0-9_]+")
DOCKER_COMPONENT_LABEL = "homelab-ha-discovery.component"
DOCKER_ENABLED_LABEL = "homelab-ha-discovery.enabled"


@dataclass(frozen=True)
class DockerContainerInfo:
    container_id: str
    name: str
    component: str
    state: str
    health: str
    restart_count: int
    labels: dict[str, str]


@dataclass(frozen=True)
class DockerContainerStats:
    cpu_usage_percent: float
    memory_usage_bytes: float
    memory_limit_bytes: float
    memory_usage_percent: float
    network_rx_bytes: float
    network_tx_bytes: float


@dataclass(frozen=True)
class DockerContainerSample:
    containers: dict[str, DockerContainerInfo]
    stats: dict[str, DockerContainerStats]
    timestamp: float


@dataclass(frozen=True)
class DockerContainerMetrics:
    component: str
    name: str
    payload: DockerMetricPayload


ZERO_STATS = DockerContainerStats(
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
        if text == DOCKER_ENABLED_LABEL:
            return text, "true"
        return text, None

    key, value = text.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"invalid label selector: {selector!r}")
    value = value.strip()
    if key == DOCKER_ENABLED_LABEL:
        if value.lower() != "true":
            raise ValueError(f"{DOCKER_ENABLED_LABEL} must be true when included")
        value = "true"
    return key, value


def labels_match_selectors(
    labels: dict[str, str],
    selectors: LabelSelectors,
) -> bool:
    for key, expected_value in selectors:
        if key not in labels:
            return False
        if key == DOCKER_ENABLED_LABEL:
            if labels[key].strip().lower() != "true":
                return False
            continue
        if expected_value is not None and labels[key] != expected_value:
            return False
    return True


def docker_component_from_name(name: str) -> str:
    component = DOCKER_COMPONENT_RE.sub("_", name.strip().lower()).strip("_")
    if not component:
        raise ValueError(f"could not derive Docker component from {name!r}")
    return component


def docker_component_from_container(
    name: str,
    labels: dict[str, str],
) -> str:
    override = labels.get(DOCKER_COMPONENT_LABEL, "").strip()
    return docker_component_from_name(override or name)


def parse_percent(value: object, field_name: str) -> float:
    text = str(value).strip()
    if text.endswith("%"):
        text = text[:-1]
    try:
        parsed = float(text)
    except ValueError as exc:
        raise ValueError(f"invalid Docker {field_name}: {value!r}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"invalid Docker {field_name}: {value!r}")
    return round(parsed, METRIC_DECIMAL_PLACES)


def parse_byte_quantity(value: object) -> float:
    text = str(value).strip()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)", text)
    if not match:
        raise ValueError(f"invalid Docker byte quantity: {value!r}")

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
        raise ValueError(f"unsupported Docker byte unit in {value!r}")

    return float(number_text) * factor


def parse_pair(value: object, field_name: str) -> tuple[float, float]:
    parts = [part.strip() for part in str(value).split("/", 1)]
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"invalid Docker {field_name}: {value!r}")
    return parse_byte_quantity(parts[0]), parse_byte_quantity(parts[1])


def container_name_from_inspect(item: dict[str, Any]) -> str:
    names = item.get("Name")
    if isinstance(names, str) and names.strip("/"):
        return names.strip("/")

    config = item.get("Config")
    if isinstance(config, dict):
        hostname = config.get("Hostname")
        if isinstance(hostname, str) and hostname.strip():
            return hostname.strip()

    container_id = str(item.get("Id", "")).strip()
    if container_id:
        return container_id[:12]
    raise ValueError("Docker inspect item is missing a container name")


def labels_from_inspect(item: dict[str, Any]) -> dict[str, str]:
    config = item.get("Config")
    if not isinstance(config, dict):
        return {}
    labels = config.get("Labels")
    if not isinstance(labels, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in labels.items()
        if value is not None
    }


def parse_docker_inspect(
    inspect_output: str,
    include_label_selectors: LabelSelectors = (),
) -> dict[str, DockerContainerInfo]:
    try:
        items = json.loads(inspect_output)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Docker inspect JSON: {exc}") from exc
    if not isinstance(items, list):
        raise ValueError("Docker inspect JSON must be a list")

    containers: dict[str, DockerContainerInfo] = {}
    components: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Docker inspect item must be an object")

        container_id = str(item.get("Id", "")).strip()
        if not container_id:
            raise ValueError("Docker inspect item is missing Id")

        labels = labels_from_inspect(item)
        if not labels_match_selectors(labels, include_label_selectors):
            continue

        state = item.get("State")
        if not isinstance(state, dict):
            state = {}
        status = str(state.get("Status") or "unknown")
        health = "none"
        health_data = state.get("Health")
        if isinstance(health_data, dict) and health_data.get("Status"):
            health = str(health_data["Status"])

        try:
            restart_count = int(item.get("RestartCount") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid Docker restart count for {container_id[:12]}"
            ) from exc

        name = container_name_from_inspect(item)
        component = docker_component_from_container(name, labels)
        previous_container = components.get(component)
        if previous_container is not None:
            raise ValueError(
                "multiple Docker containers resolve to component "
                f"{component!r}: {previous_container}, {name}"
            )
        components[component] = name
        containers[container_id] = DockerContainerInfo(
            container_id=container_id,
            name=name,
            component=component,
            state=status,
            health=health,
            restart_count=restart_count,
            labels=labels,
        )

    return containers


def parse_docker_stats_line(line: str) -> tuple[str, DockerContainerStats]:
    try:
        item = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid Docker stats JSON line: {line!r}") from exc
    if not isinstance(item, dict):
        raise ValueError(f"Docker stats line must be an object: {line!r}")

    container_key = str(item.get("ID") or item.get("Container") or "").strip()
    if not container_key:
        raise ValueError(f"Docker stats line is missing ID: {line!r}")

    memory_usage, memory_limit = parse_pair(item.get("MemUsage", ""), "MemUsage")
    network_rx, network_tx = parse_pair(item.get("NetIO", ""), "NetIO")
    return container_key, DockerContainerStats(
        cpu_usage_percent=parse_percent(item.get("CPUPerc", ""), "CPUPerc"),
        memory_usage_bytes=memory_usage,
        memory_limit_bytes=memory_limit,
        memory_usage_percent=parse_percent(item.get("MemPerc", ""), "MemPerc"),
        network_rx_bytes=network_rx,
        network_tx_bytes=network_tx,
    )


def resolve_stats_container_id(
    stats_key: str,
    containers: dict[str, DockerContainerInfo],
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


def parse_docker_stats(
    stats_output: str,
    containers: dict[str, DockerContainerInfo],
) -> dict[str, DockerContainerStats]:
    stats: dict[str, DockerContainerStats] = {}
    for line in stats_output.splitlines():
        if not line.strip():
            continue
        stats_key, parsed_stats = parse_docker_stats_line(line)
        container_id = resolve_stats_container_id(stats_key, containers)
        if container_id is not None:
            stats[container_id] = parsed_stats
    return stats


def run_docker_command(
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


def run_docker_container_ids(
    docker_command: str = "docker",
    include_all: bool = False,
) -> list[str]:
    command = [docker_command, "ps", "--no-trunc", "--quiet"]
    if include_all:
        command.append("--all")
    output = run_docker_command(command)
    return [line.strip() for line in output.splitlines() if line.strip()]


def run_docker_inspect(
    container_ids: list[str],
    docker_command: str = "docker",
) -> str:
    if not container_ids:
        return "[]"
    return run_docker_command([docker_command, "inspect", *container_ids])


def run_docker_stats(
    container_ids: list[str],
    docker_command: str = "docker",
    include_all: bool = False,
) -> str:
    if not container_ids:
        return ""
    command = [
        docker_command,
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
    ]
    if include_all:
        command.append("--all")
    command.extend(container_ids)
    return run_docker_command(command)


def read_docker_container_sample(
    docker_command: str = "docker",
    include_all: bool = False,
    include_label_selectors: LabelSelectors = (),
) -> DockerContainerSample:
    container_ids = run_docker_container_ids(
        docker_command=docker_command,
        include_all=include_all,
    )
    containers = parse_docker_inspect(
        run_docker_inspect(container_ids, docker_command=docker_command),
        include_label_selectors=include_label_selectors,
    )
    filtered_container_ids = list(containers)
    stats = parse_docker_stats(
        run_docker_stats(
            filtered_container_ids,
            docker_command=docker_command,
            include_all=include_all,
        ),
        containers,
    )
    return DockerContainerSample(
        containers=containers,
        stats=stats,
        timestamp=time.monotonic(),
    )


def stats_for_container(
    sample: DockerContainerSample,
    container: DockerContainerInfo,
) -> DockerContainerStats:
    stats = sample.stats.get(container.container_id)
    if stats is not None:
        return stats
    if container.state != "running":
        return ZERO_STATS
    raise ValueError(f"Docker stats missing for running container {container.name!r}")


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


def calculate_docker_container_metrics(
    previous: DockerContainerSample,
    current: DockerContainerSample,
) -> tuple[list[DockerContainerMetrics], list[str]]:
    elapsed_seconds = current.timestamp - previous.timestamp
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError("elapsed time between Docker samples must be greater than 0")

    metrics: list[DockerContainerMetrics] = []
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
            DockerContainerMetrics(
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
