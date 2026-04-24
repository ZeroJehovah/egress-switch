#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
DEFAULT_SYSTEMD_SERVICE_NAME="switch-ip"

load_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    return
  fi

  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

resolve_runtime_settings() {
  load_env_file
  SWITCH_IP_SYSTEMD_SERVICE_NAME="${SWITCH_IP_SYSTEMD_SERVICE_NAME-${DEFAULT_SYSTEMD_SERVICE_NAME}}"
}

is_systemd_managed_invocation() {
  [[ -n "${INVOCATION_ID:-}" ]]
}

has_systemd_service_name() {
  [[ -n "${SWITCH_IP_SYSTEMD_SERVICE_NAME}" ]]
}

run_systemctl() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl "$@"
    return
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    echo "错误: 需要 root 权限或可用的 sudo 来执行 systemctl $*" >&2
    return 1
  fi

  if ! sudo -n systemctl "$@"; then
    echo "错误: 执行 systemctl $* 失败；请确认当前用户具备免密 sudo 权限" >&2
    return 1
  fi
}

systemd_service_exists() {
  has_systemd_service_name || return 1
  command -v systemctl >/dev/null 2>&1 || return 1

  local load_state
  load_state="$(systemctl show --property=LoadState --value "${SWITCH_IP_SYSTEMD_SERVICE_NAME}" 2>/dev/null || true)"
  [[ -n "${load_state}" && "${load_state}" != "not-found" ]]
}

systemd_service_active() {
  systemd_service_exists || return 1
  systemctl is-active --quiet "${SWITCH_IP_SYSTEMD_SERVICE_NAME}"
}

resolve_runtime_settings

if ! is_systemd_managed_invocation && systemd_service_exists; then
  echo "通过 systemd 重启 switch-ip 服务: ${SWITCH_IP_SYSTEMD_SERVICE_NAME}"
  run_systemctl restart "${SWITCH_IP_SYSTEMD_SERVICE_NAME}"
  echo "switch-ip 已重启"
  exit 0
fi

"${SCRIPT_DIR}/stop.sh"
"${SCRIPT_DIR}/start.sh"
