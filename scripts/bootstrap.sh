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

echo "依赖初始化完成，准备启动 switch-ip Web 服务..."
exec "${SCRIPT_DIR}/start.sh"
