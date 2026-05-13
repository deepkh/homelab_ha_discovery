#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo or as root." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"

if command -v hhdctl >/dev/null 2>&1; then
  hhdctl_cmd=(hhdctl)
elif [[ -f "${repo_root}/src/homelab_ha_discovery/scripts/hhdctl.py" ]]; then
  hhdctl_cmd=(python3 "${repo_root}/src/homelab_ha_discovery/scripts/hhdctl.py")
else
  echo "hhdctl was not found." >&2
  exit 1
fi

common_args=()
app_args=()
detect_args=()

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --app-dir|--config-dir|--systemd-dir)
      if [[ "$#" -lt 2 ]]; then
        echo "$1 requires a value." >&2
        exit 1
      fi
      common_args+=("$1" "$2")
      detect_args+=("$1" "$2")
      shift 2
      ;;
    --dry-run)
      common_args+=("$1")
      detect_args+=("$1")
      shift
      ;;
    --force-copy|--install-system-packages)
      app_args+=("$1")
      shift
      ;;
    --bin-dir)
      if [[ "$#" -lt 2 ]]; then
        echo "$1 requires a value." >&2
        exit 1
      fi
      app_args+=("$1" "$2")
      shift 2
      ;;
    --force-config)
      detect_args+=("--force")
      shift
      ;;
    *)
      detect_args+=("$1")
      shift
      ;;
  esac
done

"${hhdctl_cmd[@]}" app install "${common_args[@]}" "${app_args[@]}"
"${hhdctl_cmd[@]}" config init-mqtt-env "${common_args[@]}"
"${hhdctl_cmd[@]}" config detect "${detect_args[@]}"

cat <<'EOF'

Next steps:
  sudo editor /etc/homelab-ha-discovery/mqtt.env
  sudo editor /etc/homelab-ha-discovery/host-metrics.json
  sudo hhdctl systemd render
  sudo hhdctl systemd enable --now
  sudo hhdctl systemd logs --follow
EOF
