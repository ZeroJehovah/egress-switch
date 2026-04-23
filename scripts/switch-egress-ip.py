#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import Settings
from app.services.native_switcher import NativeSwitchError, NativeSwitcher, read_direct_bind_address
from app.services.switch_service import normalize_target_ip


def _usage() -> int:
    print("用法:")
    print(f"  {Path(sys.argv[0]).name} 145")
    print(f"  {Path(sys.argv[0]).name} 10.0.0.145")
    return 1


def _ensure_root() -> int | None:
    if os.geteuid() == 0:
        return None

    try:
        result = subprocess.run(
            ["sudo", "-n", sys.executable, __file__, *sys.argv[1:]],
            check=False,
        )
    except FileNotFoundError:
        print("错误: 未找到 sudo，无法执行提权切换", file=sys.stderr)
        return 1

    return result.returncode


def main() -> int:
    if len(sys.argv) != 2:
        return _usage()

    delegated_code = _ensure_root()
    if delegated_code is not None:
        return delegated_code

    settings = Settings.from_env()
    target_ip = normalize_target_ip(sys.argv[1], settings.subnet_prefix)
    switcher = NativeSwitcher(settings)

    try:
        outcome = switcher.switch_ip(target_ip)
    except (ValueError, NativeSwitchError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"备份配置到: {outcome.backup_path}")
    print(f"写入 sing-box 出站绑定地址: {outcome.target_ip}")
    print("检查配置...")
    print("重启 sing-box...")
    print("服务状态:")
    print(outcome.service_status)
    print()
    print("当前 direct 出站绑定地址:")
    print(outcome.current_ip or read_direct_bind_address(settings.singbox_config_path) or "<未设置>")
    print()
    print("最近日志:")
    print(outcome.recent_logs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
