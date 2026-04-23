#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${ROOT_DIR}/.venv"
ENV_FILE="${ROOT_DIR}/.env"
REQUIREMENTS_FILE="${ROOT_DIR}/requirements.txt"
REQUIREMENTS_STAMP="${VENV_DIR}/.requirements.stamp"
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8080"
DEFAULT_PID_FILE="${ROOT_DIR}/.run/switch-ip.pid"
DEFAULT_LOG_FILE="${ROOT_DIR}/logs/switch-ip.log"

load_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    return
  fi

  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
}

ensure_python() {
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "错误: 未找到 ${PYTHON_BIN}" >&2
    exit 1
  fi
}

create_venv() {
  rm -rf "${VENV_DIR}"

  if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
    rm -rf "${VENV_DIR}"
    cat >&2 <<EOF
错误: 创建 Python 虚拟环境失败。

在 Debian/Ubuntu 上，请先安装 venv 组件，例如：
  sudo apt install python3-venv

如果你的系统使用的是特定 Python 小版本，也可能需要：
  sudo apt install python3.12-venv
EOF
    exit 1
  fi
}

venv_has_pip() {
  "${VENV_DIR}/bin/python" -m pip --version >/dev/null 2>&1
}

repair_venv_pip() {
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    return 1
  fi

  "${VENV_DIR}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1
}

ensure_venv() {
  if [[ ! -d "${VENV_DIR}" || ! -x "${VENV_DIR}/bin/python" ]]; then
    create_venv
  fi

  if ! venv_has_pip; then
    echo "检测到虚拟环境缺少 pip，正在尝试修复..."

    if ! repair_venv_pip; then
      echo "自动修复失败，正在重建虚拟环境..."
      create_venv
    fi

    if ! venv_has_pip; then
      echo "错误: 虚拟环境修复失败，仍然无法使用 pip" >&2
      echo "请先安装 python3-venv 或对应版本的 python3.x-venv 后重试" >&2
      exit 1
    fi
  fi
}

ensure_dependencies() {
  if [[ -f "${REQUIREMENTS_STAMP}" && "${REQUIREMENTS_STAMP}" -nt "${REQUIREMENTS_FILE}" ]]; then
    return
  fi

  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/python" -m pip install -r "${REQUIREMENTS_FILE}"
  touch "${REQUIREMENTS_STAMP}"
}

ensure_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${ROOT_DIR}/.env.example" "${ENV_FILE}"
  fi
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

  if [[ "${SWITCH_IP_PID_FILE}" != /* ]]; then
    SWITCH_IP_PID_FILE="${ROOT_DIR}/${SWITCH_IP_PID_FILE}"
  fi

  if [[ "${SWITCH_IP_LOG_FILE}" != /* ]]; then
    SWITCH_IP_LOG_FILE="${ROOT_DIR}/${SWITCH_IP_LOG_FILE}"
  fi

  mkdir -p "$(dirname "${SWITCH_IP_PID_FILE}")" "$(dirname "${SWITCH_IP_LOG_FILE}")"
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
