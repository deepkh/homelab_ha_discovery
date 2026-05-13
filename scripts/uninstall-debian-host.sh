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

"${hhdctl_cmd[@]}" systemd uninstall "$@"

echo "Generated systemd units were removed. App and config directories were left in place."
