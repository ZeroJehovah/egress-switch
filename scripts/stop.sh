#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

ensure_runtime_dirs
resolve_runtime_settings

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
