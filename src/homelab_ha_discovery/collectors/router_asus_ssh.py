"""Collect ASUS router metrics over SSH."""

from __future__ import annotations

import ipaddress
import json
import math
import re
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any


RouterCpuMetrics = dict[str, float]
RouterConnectedClient = dict[str, str]
RouterConnectedClients = list[RouterConnectedClient]
RouterNetworkMetrics = dict[str, float]

DEFAULT_SSH_PORT = 22
DEFAULT_SSH_COMMAND_TIMEOUT_SECONDS = 10.0
DEFAULT_TOP_COMMAND = "top -bn1"
DEFAULT_TEMPERATURE_COMMAND = "cat /sys/class/thermal/thermal_zone*/temp"
DEFAULT_CLIENT_LIST_COMMAND = (
    'cat /var/lib/misc/dnsmasq.leases; echo "---END_LEASES---"; '
    "cat /tmp/clientlist.json"
)
DEFAULT_NETWORK_SAMPLE_INTERVAL_SECONDS = 1.0
BITS_PER_MEGABIT = 1000_000.0
NETWORK_SPEED_DECIMAL_PLACES = 3
CLIENT_LIST_SEPARATOR = "---END_LEASES---"
SSH_OPTIONS = (
    "-o",
    "ConnectTimeout=5",
    "-o",
    "BatchMode=yes",
)
CPU_IDLE_RE = re.compile(
    r"(?P<idle>\d+(?:\.\d+)?)\s*%?\s*(?:id|idle)\b",
    re.IGNORECASE,
)
THERMAL_TEMP_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
NETWORK_SAMPLE_RE = re.compile(
    r"^sample(?P<sample>[12])\s+(?P<rx>\d+)\s+(?P<tx>\d+)\s*$",
    re.IGNORECASE,
)
NETWORK_METRIC_RE = re.compile(
    r"^(?P<metric>download|upload)_mbps\s+(?P<value>[+-]?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)
MAC_RE = re.compile(r"(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
WIRELESS_INTERFACE_RE = re.compile(r"^\d+G(?:-\d+)?$", re.IGNORECASE)
WIRED_INTERFACE_KEYS = {
    "wired",
    "wired_mac",
}
NO_DHCP_HOSTNAMES = {
    "",
    "*",
}
DEBUG_LIST_LIMIT = 8
DEBUG_TOP_LEVEL_LIMIT = 20
DEBUG_NESTED_INTERFACE_LIMIT = 20


def require_ssh_value(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def validate_ssh_port(port: object) -> int:
    try:
        port_number = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError("ssh port must be an integer") from exc
    if isinstance(port, float) and not port.is_integer():
        raise ValueError("ssh port must be an integer")
    if port_number <= 0 or port_number > 65535:
        raise ValueError("ssh port must be between 1 and 65535")
    return port_number


def require_network_interface(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("network interface is required")
    return value.strip()


def run_asus_router_ssh_command(
    ssh_user: str,
    ssh_ip: str,
    remote_command: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    timeout: float = DEFAULT_SSH_COMMAND_TIMEOUT_SECONDS,
) -> str:
    user = require_ssh_value(ssh_user, "ssh user")
    ip_address = require_ssh_value(ssh_ip, "ssh ip")
    port = validate_ssh_port(ssh_port)
    command = [
        "ssh",
        *SSH_OPTIONS,
        "-p",
        str(port),
        f"{user}@{ip_address}",
        remote_command,
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        detail = f": {stderr}" if stderr else ""
        raise RuntimeError(
            "ASUS router SSH command failed "
            f"({remote_command!r}) with exit code {exc.returncode}{detail}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "ASUS router SSH command timed out "
            f"after {timeout:g} seconds ({remote_command!r})"
        ) from exc
    return result.stdout


def run_asus_router_top(
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    top_command: str = DEFAULT_TOP_COMMAND,
) -> str:
    return run_asus_router_ssh_command(
        ssh_user,
        ssh_ip,
        top_command,
        ssh_port=ssh_port,
    )


def run_asus_router_thermal_temps(
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    temperature_command: str = DEFAULT_TEMPERATURE_COMMAND,
) -> str:
    return run_asus_router_ssh_command(
        ssh_user,
        ssh_ip,
        temperature_command,
        ssh_port=ssh_port,
    )


def run_asus_router_client_list(
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    client_list_command: str = DEFAULT_CLIENT_LIST_COMMAND,
) -> str:
    return run_asus_router_ssh_command(
        ssh_user,
        ssh_ip,
        client_list_command,
        ssh_port=ssh_port,
    )


def build_asus_router_network_command(interface: str) -> str:
    dev = shlex.quote(require_network_interface(interface))
    return " ".join(
        (
            f"dev={dev};",
            "read_counters() {",
            "awk -v iface=\"$dev:\" "
            "'$1 == iface { print $2, $10; found=1 } "
            "END { if (!found) exit 2 }' /proc/net/dev;",
            "};",
            "sample1=$(read_counters) || exit 2;",
            "set -- $sample1;",
            "rx1=$1;",
            "tx1=$2;",
            "sleep 1;",
            "sample2=$(read_counters) || exit 2;",
            "set -- $sample2;",
            "rx2=$1;",
            "tx2=$2;",
            "[ \"$rx2\" -ge \"$rx1\" ] || exit 3;",
            "[ \"$tx2\" -ge \"$tx1\" ] || exit 3;",
            "printf 'sample1 %s %s\\nsample2 %s %s\\n' "
            "\"$rx1\" \"$tx1\" \"$rx2\" \"$tx2\";",
            "awk -v rx1=\"$rx1\" -v tx1=\"$tx1\" "
            "-v rx2=\"$rx2\" -v tx2=\"$tx2\" "
            "'BEGIN { printf "
            "\"download_mbps %.6f\\nupload_mbps %.6f\\n\", "
            "(rx2 - rx1) * 8 / 1000000, "
            "(tx2 - tx1) * 8 / 1000000 }'",
        )
    )


def run_asus_router_network(
    ssh_user: str,
    ssh_ip: str,
    interface: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    network_command: str | None = None,
) -> str:
    return run_asus_router_ssh_command(
        ssh_user,
        ssh_ip,
        network_command or build_asus_router_network_command(interface),
        ssh_port=ssh_port,
    )


def parse_asus_router_cpu_usage(top_output: str) -> float:
    for line in top_output.splitlines():
        if "cpu" not in line.lower():
            continue

        idle_match = CPU_IDLE_RE.search(line)
        if not idle_match:
            continue

        idle_percent = float(idle_match.group("idle"))
        return round(max(0.0, min(100.0, 100.0 - idle_percent)), 1)

    raise ValueError("Could not find ASUS router CPU idle percentage in top output")


def parse_asus_router_cpu_temperature(thermal_output: str) -> float:
    temperatures = []
    for line in thermal_output.splitlines():
        raw_value = line.strip()
        if not raw_value or not THERMAL_TEMP_RE.fullmatch(raw_value):
            continue

        temperature = float(raw_value) / 1000.0
        if math.isfinite(temperature) and temperature >= 0:
            temperatures.append(temperature)

    if not temperatures:
        raise ValueError("Could not find ASUS router thermal zone temperature")

    return round(max(temperatures), 1)


def calculate_asus_router_network_speed_metrics(
    previous_rx_bytes: int,
    previous_tx_bytes: int,
    current_rx_bytes: int,
    current_tx_bytes: int,
    elapsed_seconds: float = DEFAULT_NETWORK_SAMPLE_INTERVAL_SECONDS,
) -> RouterNetworkMetrics:
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError("elapsed time between network samples must be greater than 0")

    rx_delta = current_rx_bytes - previous_rx_bytes
    tx_delta = current_tx_bytes - previous_tx_bytes
    if rx_delta < 0 or tx_delta < 0:
        raise ValueError("ASUS router network byte counters decreased unexpectedly")

    return {
        "Download Speed": round(
            rx_delta * 8 / elapsed_seconds / BITS_PER_MEGABIT,
            NETWORK_SPEED_DECIMAL_PLACES,
        ),
        "Upload Speed": round(
            tx_delta * 8 / elapsed_seconds / BITS_PER_MEGABIT,
            NETWORK_SPEED_DECIMAL_PLACES,
        ),
    }


def parse_asus_router_network_metrics(network_output: str) -> RouterNetworkMetrics:
    samples: dict[int, tuple[int, int]] = {}
    metrics: dict[str, float] = {}
    malformed_lines: list[str] = []

    for line in network_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        sample_match = NETWORK_SAMPLE_RE.fullmatch(stripped)
        if sample_match:
            samples[int(sample_match.group("sample"))] = (
                int(sample_match.group("rx")),
                int(sample_match.group("tx")),
            )
            continue

        metric_match = NETWORK_METRIC_RE.fullmatch(stripped)
        if metric_match:
            value = float(metric_match.group("value"))
            if not math.isfinite(value) or value < 0:
                raise ValueError("ASUS router network Mbps values must be non-negative")
            metrics[metric_match.group("metric").lower()] = value
            continue

        malformed_lines.append(stripped)

    if 1 in samples or 2 in samples:
        if 1 not in samples or 2 not in samples:
            raise ValueError("ASUS router network output is missing a sample line")
        previous_rx, previous_tx = samples[1]
        current_rx, current_tx = samples[2]
        return calculate_asus_router_network_speed_metrics(
            previous_rx,
            previous_tx,
            current_rx,
            current_tx,
        )

    if {"download", "upload"} <= set(metrics):
        return {
            "Download Speed": round(
                metrics["download"],
                NETWORK_SPEED_DECIMAL_PLACES,
            ),
            "Upload Speed": round(
                metrics["upload"],
                NETWORK_SPEED_DECIMAL_PLACES,
            ),
        }

    if malformed_lines:
        raise ValueError(
            "Could not parse ASUS router network output line: "
            f"{malformed_lines[0]!r}"
        )
    raise ValueError("ASUS router network output is missing speed metrics")


def normalize_mac_address(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = MAC_RE.search(value.strip())
    if match is None:
        return None
    return match.group(0).upper()


def find_ipv4_address(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    for match in IPV4_RE.finditer(value):
        ip_address = match.group(0)
        try:
            ipaddress.IPv4Address(ip_address)
        except ipaddress.AddressValueError:
            continue
        return ip_address
    return None


def normalize_dhcp_hostname(value: object) -> str:
    if not isinstance(value, str):
        return " - "
    hostname = value.strip()
    if hostname in NO_DHCP_HOSTNAMES:
        return " - "
    return hostname


def parse_dnsmasq_leases(
    leases_output: str,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    leases_by_mac: dict[str, dict[str, str]] = {}
    leases_by_ip: dict[str, dict[str, str]] = {}

    for line in leases_output.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue

        mac = normalize_mac_address(fields[1])
        ip_address = find_ipv4_address(fields[2])
        if mac is None or ip_address is None:
            continue

        lease = {
            "ip": ip_address,
            "name": normalize_dhcp_hostname(fields[3] if len(fields) > 3 else ""),
        }
        existing_mac_lease = leases_by_mac.get(mac)
        if existing_mac_lease is None or lease["name"] != " - ":
            leases_by_mac[mac] = lease

        existing_ip_lease = leases_by_ip.get(ip_address)
        if existing_ip_lease is None or lease["name"] != " - ":
            leases_by_ip[ip_address] = lease

    return leases_by_mac, leases_by_ip


def debug_list(values: Sequence[str], limit: int = DEBUG_LIST_LIMIT) -> str:
    if not values:
        return "[]"
    shown = ", ".join(repr(value) for value in values[:limit])
    if len(values) > limit:
        shown += f", ... (+{len(values) - limit} more)"
    return f"[{shown}]"


def json_node_summary(value: Any) -> str:
    if isinstance(value, Mapping):
        return f"dict keys={len(value)}"
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return f"list items={len(value)}"
    if isinstance(value, str):
        return f"str chars={len(value)}"
    return type(value).__name__


def json_path_child(path: str, key: object) -> str:
    return f"{path}[{key!r}]"


def parse_clientlist_json(clientlist_output: str) -> dict[str, Any]:
    raw_json = clientlist_output.strip()
    if not raw_json:
        raise ValueError("ASUS router clientlist.json output is empty")

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        start = raw_json.find("{")
        end = raw_json.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw_json[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("ASUS router clientlist.json must be a JSON object")
    return parsed


def collect_mac_addresses(value: Any) -> list[str]:
    seen: set[str] = set()
    macs: list[str] = []

    def add_mac(raw_value: object) -> None:
        if not isinstance(raw_value, str):
            return
        for match in MAC_RE.finditer(raw_value):
            mac = match.group(0).upper()
            if mac not in seen:
                seen.add(mac)
                macs.append(mac)

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, item in node.items():
                add_mac(str(key))
                walk(item)
            return
        if isinstance(node, Sequence) and not isinstance(node, (bytes, bytearray, str)):
            for item in node:
                walk(item)
            return
        add_mac(node)

    walk(value)
    return macs


def debug_client_samples(clients: RouterConnectedClients) -> list[str]:
    return [
        (
            f"{client['mac']} ip={client['ip'] or '<empty>'} "
            f"rssi={client['rssi']} interface={client['interface']}"
        )
        for client in clients[:DEBUG_LIST_LIMIT]
    ]


def nested_interface_debug_lines(
    value: Any,
    path: str = "$",
    lines: list[str] | None = None,
) -> list[str]:
    if lines is None:
        lines = []
    if len(lines) >= DEBUG_NESTED_INTERFACE_LIMIT:
        return lines

    if isinstance(value, Mapping):
        for key, item in value.items():
            if len(lines) >= DEBUG_NESTED_INTERFACE_LIMIT:
                break
            child_path = json_path_child(path, key)
            if is_client_interface_key(key):
                clients = extract_clients_from_interface(str(key), item)
                macs = collect_mac_addresses(item)
                line = (
                    f"nested interface candidate {child_path}: "
                    f"{json_node_summary(item)}, macs={len(macs)}, "
                    f"extracted_clients={len(clients)}"
                )
                samples = debug_client_samples(clients)
                if samples:
                    line += f", sample_clients={debug_list(samples)}"
                lines.append(line)
            if isinstance(item, (Mapping, list, tuple)):
                nested_interface_debug_lines(item, child_path, lines)
        return lines

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for index, item in enumerate(value):
            if len(lines) >= DEBUG_NESTED_INTERFACE_LIMIT:
                break
            if isinstance(item, (Mapping, list, tuple)):
                nested_interface_debug_lines(item, f"{path}[{index}]", lines)
    return lines


def asus_router_connected_clients_debug_lines(combined_output: str) -> list[str]:
    lines = [
        (
            f"combined_output_chars={len(combined_output)}, "
            f"separator_present={CLIENT_LIST_SEPARATOR in combined_output}"
        )
    ]
    if CLIENT_LIST_SEPARATOR not in combined_output:
        return lines

    leases_output, clientlist_output = combined_output.split(CLIENT_LIST_SEPARATOR, 1)
    lease_lines = [line for line in leases_output.splitlines() if line.strip()]
    leases_by_mac, leases_by_ip = parse_dnsmasq_leases(leases_output)
    lines.append(
        "dnsmasq leases: "
        f"nonempty_lines={len(lease_lines)}, "
        f"parsed_macs={len(leases_by_mac)}, parsed_ips={len(leases_by_ip)}"
    )
    lease_samples = [
        f"{mac}->{lease['ip']}/{lease['name']}"
        for mac, lease in list(leases_by_mac.items())[:DEBUG_LIST_LIMIT]
    ]
    if lease_samples:
        lines.append(f"dnsmasq lease samples={debug_list(lease_samples)}")

    raw_clientlist = clientlist_output.strip()
    lines.append(f"clientlist_json_chars={len(raw_clientlist)}")
    try:
        clientlist = parse_clientlist_json(clientlist_output)
    except Exception as exc:
        lines.append(f"clientlist JSON parse error: {exc}")
        return lines

    top_keys = [str(key) for key in clientlist.keys()]
    interface_keys = [key for key in top_keys if is_client_interface_key(key)]
    all_macs = collect_mac_addresses(clientlist)
    lines.append(
        f"clientlist top-level keys ({len(top_keys)}): {debug_list(top_keys)}"
    )
    lines.append(
        "clientlist top-level interface keys "
        f"({len(interface_keys)}): {debug_list(interface_keys)}"
    )
    lines.append(
        f"clientlist unique MAC strings anywhere={len(all_macs)}: "
        f"{debug_list(all_macs)}"
    )

    for key, section in list(clientlist.items())[:DEBUG_TOP_LEVEL_LIMIT]:
        key_text = str(key)
        key_mac = normalize_mac_address(key_text)
        section_macs = collect_mac_addresses(section)
        line = (
            f"top-level key {key_text!r}: {json_node_summary(section)}, "
            f"key_is_mac={key_mac is not None}, "
            f"section_macs={len(section_macs)}"
        )
        if section_macs:
            line += f", sample_macs={debug_list(section_macs)}"
        if is_client_interface_key(key_text):
            clients = extract_clients_from_interface(key_text, section)
            line += f", extracted_clients={len(clients)}"
            samples = debug_client_samples(clients)
            if samples:
                line += f", sample_clients={debug_list(samples)}"
        lines.append(line)
    if len(clientlist) > DEBUG_TOP_LEVEL_LIMIT:
        lines.append(
            "top-level keys omitted from debug: "
            f"{len(clientlist) - DEBUG_TOP_LEVEL_LIMIT}"
        )

    nested_lines = nested_interface_debug_lines(clientlist)
    if nested_lines:
        lines.extend(nested_lines)
    else:
        lines.append("nested interface candidates: none")

    return lines


def is_client_interface_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip()
    return (
        normalized.lower() in WIRED_INTERFACE_KEYS
        or WIRELESS_INTERFACE_RE.fullmatch(normalized) is not None
    )


def value_for_normalized_key(
    mapping: Mapping[str, Any],
    normalized_keys: set[str],
) -> Any:
    for key, value in mapping.items():
        normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in normalized_keys:
            return value
    return None


def find_shallow_mac(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            mac = normalize_mac_address(key)
            if mac is not None:
                return mac
            mac = normalize_mac_address(item)
            if mac is not None:
                return mac
    elif isinstance(value, str):
        return normalize_mac_address(value)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for item in value:
            mac = normalize_mac_address(item)
            if mac is not None:
                return mac
    return None


def find_shallow_ip(value: Any) -> str | None:
    if isinstance(value, Mapping):
        explicit_ip = value_for_normalized_key(
            value,
            {"ip", "ip_addr", "ip_address", "ipaddr", "address"},
        )
        ip_address = find_ipv4_address(str(explicit_ip)) if explicit_ip else None
        if ip_address is not None:
            return ip_address
        for item in value.values():
            ip_address = find_ipv4_address(str(item))
            if ip_address is not None:
                return ip_address
    elif isinstance(value, str):
        return find_ipv4_address(value)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for item in value:
            ip_address = find_ipv4_address(str(item))
            if ip_address is not None:
                return ip_address
    return None


def normalize_rssi(value: object) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)) and -120 <= float(value) < 0:
            return str(int(value)) if float(value).is_integer() else str(value)
        return None
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        numeric = float(stripped)
    except ValueError:
        return None
    if not math.isfinite(numeric) or numeric < -120 or numeric >= 0:
        return None
    return str(int(numeric)) if numeric.is_integer() else stripped


def find_shallow_rssi(value: Any) -> str | None:
    if isinstance(value, Mapping):
        explicit_rssi = value_for_normalized_key(
            value,
            {"rssi", "signal", "signal_strength", "wireless_rssi"},
        )
        rssi = normalize_rssi(explicit_rssi)
        if rssi is not None:
            return rssi
        for item in value.values():
            rssi = normalize_rssi(item)
            if rssi is not None:
                return rssi
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for item in value:
            rssi = normalize_rssi(item)
            if rssi is not None:
                return rssi
    return None


def client_record_from_node(
    interface: str,
    node: Any,
    mac_hint: str | None = None,
) -> RouterConnectedClient | None:
    mac = mac_hint or find_shallow_mac(node)
    if mac is None:
        return None
    ip_address = find_shallow_ip(node) or ""
    rssi = find_shallow_rssi(node) or "N/A"
    return {
        "mac": mac,
        "ip": ip_address,
        "rssi": rssi,
        "interface": interface,
        "name": " - ",
    }


def extract_clients_from_interface(
    interface: str,
    section: Any,
) -> RouterConnectedClients:
    clients: RouterConnectedClients = []
    seen: set[str] = set()

    def add_client(client: RouterConnectedClient | None) -> None:
        if client is None or client["mac"] in seen:
            return
        seen.add(client["mac"])
        clients.append(client)

    def walk(node: Any, mac_hint: str | None = None) -> None:
        if mac_hint is not None:
            add_client(client_record_from_node(interface, node, mac_hint))
            return

        if isinstance(node, Mapping):
            keyed_client_found = False
            for key, value in node.items():
                mac = normalize_mac_address(key)
                if mac is None:
                    continue
                keyed_client_found = True
                add_client(client_record_from_node(interface, value, mac))
            if keyed_client_found:
                return

            own_mac = find_shallow_mac(node)
            if own_mac is not None:
                add_client(client_record_from_node(interface, node, own_mac))
                return

            for value in node.values():
                walk(value)
            return

        if isinstance(node, Sequence) and not isinstance(node, (bytes, bytearray, str)):
            shallow_macs = [
                mac
                for item in node
                if (mac := normalize_mac_address(item)) is not None
            ]
            if len(shallow_macs) > 1 and find_shallow_ip(node) is None:
                for item in node:
                    walk(item)
                return

            own_mac = shallow_macs[0] if shallow_macs else find_shallow_mac(node)
            if own_mac is not None:
                add_client(client_record_from_node(interface, node, own_mac))
                return

            for item in node:
                walk(item)
            return

        add_client(client_record_from_node(interface, node))

    walk(section)
    return clients


def enrich_clients_from_leases(
    clients: RouterConnectedClients,
    leases_by_mac: dict[str, dict[str, str]],
    leases_by_ip: dict[str, dict[str, str]],
) -> RouterConnectedClients:
    enriched_clients: RouterConnectedClients = []

    for client in clients:
        enriched_client = dict(client)
        mac_lease = leases_by_mac.get(enriched_client["mac"])
        if not enriched_client["ip"] and mac_lease is not None:
            enriched_client["ip"] = mac_lease["ip"]

        lease = mac_lease
        if (
            (lease is None or lease["name"] == " - ")
            and enriched_client["ip"] in leases_by_ip
        ):
            lease = leases_by_ip[enriched_client["ip"]]
        if lease is not None:
            enriched_client["name"] = lease["name"]
        enriched_clients.append(enriched_client)

    return enriched_clients


def parse_asus_router_connected_clients(
    combined_output: str,
) -> RouterConnectedClients:
    if CLIENT_LIST_SEPARATOR not in combined_output:
        raise ValueError(
            f"ASUS router connected-client output is missing {CLIENT_LIST_SEPARATOR!r}"
        )

    leases_output, clientlist_output = combined_output.split(CLIENT_LIST_SEPARATOR, 1)
    leases_by_mac, leases_by_ip = parse_dnsmasq_leases(leases_output)
    clientlist = parse_clientlist_json(clientlist_output)

    clients: RouterConnectedClients = []
    seen: set[str] = set()

    def add_client(client: RouterConnectedClient | None) -> None:
        if client is None or client["mac"] in seen:
            return
        seen.add(client["mac"])
        clients.append(client)

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if is_client_interface_key(key):
                    for client in extract_clients_from_interface(str(key), value):
                        add_client(client)
                if isinstance(value, (Mapping, list, tuple)):
                    walk(value)
            return

        if isinstance(node, Sequence) and not isinstance(node, (bytes, bytearray, str)):
            for item in node:
                if isinstance(item, (Mapping, list, tuple)):
                    walk(item)

    walk(clientlist)

    return enrich_clients_from_leases(clients, leases_by_mac, leases_by_ip)


def collect_asus_router_cpu_metrics(
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    top_command: str = DEFAULT_TOP_COMMAND,
    temperature_command: str = DEFAULT_TEMPERATURE_COMMAND,
) -> RouterCpuMetrics:
    return {
        "CPU Usages": parse_asus_router_cpu_usage(
            run_asus_router_top(
                ssh_user,
                ssh_ip,
                ssh_port=ssh_port,
                top_command=top_command,
            )
        ),
        "Temperature": parse_asus_router_cpu_temperature(
            run_asus_router_thermal_temps(
                ssh_user,
                ssh_ip,
                ssh_port=ssh_port,
                temperature_command=temperature_command,
            )
        ),
    }


def collect_asus_router_connected_clients(
    ssh_user: str,
    ssh_ip: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    client_list_command: str = DEFAULT_CLIENT_LIST_COMMAND,
) -> RouterConnectedClients:
    return parse_asus_router_connected_clients(
        run_asus_router_client_list(
            ssh_user,
            ssh_ip,
            ssh_port=ssh_port,
            client_list_command=client_list_command,
        )
    )


def collect_asus_router_network_metrics(
    ssh_user: str,
    ssh_ip: str,
    interface: str,
    ssh_port: int = DEFAULT_SSH_PORT,
    network_command: str | None = None,
) -> RouterNetworkMetrics:
    return parse_asus_router_network_metrics(
        run_asus_router_network(
            ssh_user,
            ssh_ip,
            interface,
            ssh_port=ssh_port,
            network_command=network_command,
        )
    )
