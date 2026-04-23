#!/usr/bin/env bash
set -euo pipefail

CONFIG="${SINGBOX_CONFIG_PATH:-/etc/sing-box/config.json}"
SERVICE="${SINGBOX_SERVICE_NAME:-sing-box}"
IFACE="${SWITCH_IP_INTERFACE:-enp0s6}"
SUBNET_PREFIX="${SWITCH_IP_SUBNET_PREFIX:-10.0.0}"
SINGBOX_BIN="${SINGBOX_BIN:-sing-box}"

usage() {
  echo "用法:"
  echo "  $0 145"
  echo "  $0 10.0.0.145"
  exit 1
}

if [[ $# -ne 1 ]]; then
  usage
fi

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  if ! sudo -n true >/dev/null 2>&1; then
    echo "错误: 当前用户不是 root，且未配置免密 sudo，无法执行切换" >&2
    exit 1
  fi
  SUDO="sudo -n"
fi

INPUT="$1"

if [[ "${INPUT}" =~ ^[0-9]{1,3}$ ]]; then
  OCTET="${INPUT}"
  if (( OCTET < 0 || OCTET > 255 )); then
    echo "错误: 最后一段必须在 0-255" >&2
    exit 1
  fi
  TARGET_IP="${SUBNET_PREFIX}.${OCTET}"
elif [[ "${INPUT}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  TARGET_IP="${INPUT}"
else
  echo "错误: 参数格式不对" >&2
  usage
fi

if ! ip -o -4 addr show dev "${IFACE}" | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "${TARGET_IP}"; then
  echo "错误: ${TARGET_IP} 没有绑定在接口 ${IFACE} 上" >&2
  echo "当前 ${IFACE} 上的 IPv4:" >&2
  ip -o -4 addr show dev "${IFACE}" | awk '{print "  - " $4}' >&2
  exit 1
fi

TS="$(date +%F-%H%M%S)"
BACKUP="${CONFIG}.bak.${TS}"

echo "备份配置到: ${BACKUP}"
${SUDO} cp "${CONFIG}" "${BACKUP}"

echo "写入 sing-box 出站绑定地址: ${TARGET_IP}"
${SUDO} python3 - "${CONFIG}" "${TARGET_IP}" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
target_ip = sys.argv[2]

data = json.loads(config_path.read_text(encoding="utf-8"))

outbounds = data.get("outbounds", [])
found = False
for outbound in outbounds:
    if outbound.get("tag") == "direct":
        outbound["inet4_bind_address"] = target_ip
        found = True
        break

if not found:
    raise SystemExit("没有找到 tag 为 direct 的 outbound")

config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "检查配置..."
if ! (cd "$(dirname "${CONFIG}")" && ${SUDO} "${SINGBOX_BIN}" check); then
  echo "配置检查失败，正在恢复备份..." >&2
  ${SUDO} cp "${BACKUP}" "${CONFIG}"
  exit 1
fi

echo "重启 sing-box..."
${SUDO} systemctl restart "${SERVICE}"

echo "服务状态:"
${SUDO} systemctl --no-pager --full status "${SERVICE}" | sed -n '1,12p'

echo
echo "当前 direct 出站绑定地址:"
${SUDO} python3 - "${CONFIG}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)

for outbound in config.get("outbounds", []):
    if outbound.get("tag") == "direct":
        print(outbound.get("inet4_bind_address", "<未设置>"))
        break
PY

echo
echo "最近日志:"
${SUDO} journalctl -u "${SERVICE}" -n 8 --no-pager
