#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

ensure_python
ensure_venv
ensure_dependencies
ensure_env_file
ensure_runtime_dirs
resolve_runtime_settings

if pid="$(read_pid "${SWITCH_IP_PID_FILE}")" && is_running "${pid}"; then
  echo "switch-ip 已在运行，PID=${pid}"
  echo "访问地址: http://${SWITCH_IP_HOST}:${SWITCH_IP_PORT}"
  exit 0
fi

if [[ -f "${SWITCH_IP_PID_FILE}" ]]; then
  rm -f "${SWITCH_IP_PID_FILE}"
fi

echo "启动 switch-ip..."
echo "日志文件: ${SWITCH_IP_LOG_FILE}"

(
  cd "${ROOT_DIR}"
  nohup "${VENV_DIR}/bin/python" -m app.web >> "${SWITCH_IP_LOG_FILE}" 2>&1 &
  echo $! > "${SWITCH_IP_PID_FILE}"
)

sleep 1

pid="$(read_pid "${SWITCH_IP_PID_FILE}")"
if ! is_running "${pid}"; then
  echo "错误: switch-ip 启动失败，请检查日志 ${SWITCH_IP_LOG_FILE}" >&2
  exit 1
fi

echo "switch-ip 已启动，PID=${pid}"
echo "访问地址: http://${SWITCH_IP_HOST}:${SWITCH_IP_PORT}"
