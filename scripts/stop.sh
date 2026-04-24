#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8080"
DEFAULT_PID_FILE="${ROOT_DIR}/.run/switch-ip.pid"
DEFAULT_LOG_FILE="${ROOT_DIR}/logs/switch-ip.log"
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

ensure_runtime_dirs() {
  mkdir -p "${ROOT_DIR}/.run" "${ROOT_DIR}/logs"
}

resolve_runtime_settings() {
  load_env_file
  SWITCH_IP_HOST="${SWITCH_IP_HOST:-${DEFAULT_HOST}}"
  SWITCH_IP_PORT="${SWITCH_IP_PORT:-${DEFAULT_PORT}}"
  SWITCH_IP_PID_FILE="${SWITCH_IP_PID_FILE:-${DEFAULT_PID_FILE}}"
  SWITCH_IP_LOG_FILE="${SWITCH_IP_LOG_FILE:-${DEFAULT_LOG_FILE}}"
  SWITCH_IP_SYSTEMD_SERVICE_NAME="${SWITCH_IP_SYSTEMD_SERVICE_NAME-${DEFAULT_SYSTEMD_SERVICE_NAME}}"

  if [[ "${SWITCH_IP_PID_FILE}" != /* ]]; then
    SWITCH_IP_PID_FILE="${ROOT_DIR}/${SWITCH_IP_PID_FILE}"
  fi

  if [[ "${SWITCH_IP_LOG_FILE}" != /* ]]; then
    SWITCH_IP_LOG_FILE="${ROOT_DIR}/${SWITCH_IP_LOG_FILE}"
  fi

  mkdir -p "$(dirname "${SWITCH_IP_PID_FILE}")" "$(dirname "${SWITCH_IP_LOG_FILE}")"
}

is_systemd_managed_invocation() {
  [[ -n "${INVOCATION_ID:-}" ]]
}

has_systemd_service_name() {
  [[ -n "${SWITCH_IP_SYSTEMD_SERVICE_NAME}" ]]
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

read_pid() {
  local pid_file="$1"

  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi

  local pid
  pid="$(tr -d '[:space:]' < "${pid_file}")"
  if [[ -z "${pid}" ]]; then
    return 1
  fi

  printf '%s\n' "${pid}"
}

is_running() {
  local pid="$1"
  kill -0 "${pid}" >/dev/null 2>&1
}

ensure_runtime_dirs
resolve_runtime_settings

if ! is_systemd_managed_invocation && systemd_service_active; then
  echo "通过 systemd 停止 switch-ip 服务: ${SWITCH_IP_SYSTEMD_SERVICE_NAME}"
  systemctl stop "${SWITCH_IP_SYSTEMD_SERVICE_NAME}"
  echo "switch-ip 已停止"
  exit 0
fi

if ! pid="$(read_pid "${SWITCH_IP_PID_FILE}")"; then
  echo "switch-ip 未运行"
  exit 0
fi

if ! is_running "${pid}"; then
  rm -f "${SWITCH_IP_PID_FILE}"
  echo "switch-ip 进程不存在，已清理陈旧 PID 文件"
  exit 0
fi

echo "停止 switch-ip，PID=${pid}"
kill "${pid}"

for _ in {1..20}; do
  if ! is_running "${pid}"; then
    rm -f "${SWITCH_IP_PID_FILE}"
    echo "switch-ip 已停止"
    exit 0
  fi
  sleep 1
done

echo "进程未在预期时间内退出，执行强制停止"
kill -9 "${pid}"
rm -f "${SWITCH_IP_PID_FILE}"
echo "switch-ip 已强制停止"
