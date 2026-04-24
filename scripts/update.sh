#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "错误: 当前存在未提交的已跟踪改动，拒绝执行 git pull" >&2
  exit 1
fi

echo "拉取最新代码..."
git pull --ff-only

"${SCRIPT_DIR}/restart.sh"
