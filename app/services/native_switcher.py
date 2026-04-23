from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.services.public_ip_service import PublicIPv4Service


def _default_runner(
    command: list[str],
    timeout: int,
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )


class NativeSwitchError(RuntimeError):
    pass


@dataclass(slots=True)
class NativeSwitchOutcome:
    target_ip: str
    backup_path: Path
    current_ip: str | None
    public_ipv4: str | None
    public_ipv4_updated_at: str | None
    public_ipv4_error: str | None
    service_status: str
    recent_logs: str


def _read_config(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


def read_direct_bind_address(config_path: Path) -> str | None:
    data = _read_config(config_path)
    for outbound in data.get("outbounds", []):
        if outbound.get("tag") == "direct":
            value = outbound.get("inet4_bind_address")
            return str(value) if value else None
    raise NativeSwitchError("没有找到 tag 为 direct 的 outbound")


def write_direct_bind_address(config_path: Path, target_ip: str) -> None:
    data = _read_config(config_path)
    outbounds = data.get("outbounds", [])

    for outbound in outbounds:
        if outbound.get("tag") == "direct":
            outbound["inet4_bind_address"] = target_ip
            config_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return

    raise NativeSwitchError("没有找到 tag 为 direct 的 outbound")


def list_interface_ipv4_addresses(
    interface: str,
    timeout: int,
    runner=_default_runner,
) -> list[str]:
    result = runner(
        ["ip", "-o", "-4", "addr", "show", "dev", interface],
        timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
        raise NativeSwitchError(detail)

    addresses: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue

        address = parts[3].split("/", 1)[0]
        try:
            ipaddress.IPv4Address(address)
        except ValueError:
            continue

        addresses.append(address)

    return sorted(set(addresses), key=ipaddress.IPv4Address)


class NativeSwitcher:
    def __init__(
        self,
        settings: Settings,
        runner=_default_runner,
        public_ip_service: PublicIPv4Service | None = None,
    ) -> None:
        self.settings = settings
        self.runner = runner
        self.public_ip_service = public_ip_service or PublicIPv4Service(settings)

    def switch_ip(self, target_ip: str) -> NativeSwitchOutcome:
        config_path = Path(self.settings.singbox_config_path)
        self.ensure_target_ip_is_bound(target_ip)

        timestamp = datetime.now().strftime("%F-%H%M%S")
        backup_path = config_path.with_name(f"{config_path.name}.bak.{timestamp}")
        shutil.copy2(config_path, backup_path)

        write_direct_bind_address(config_path, target_ip)

        check_result = self.runner(
            [self.settings.singbox_bin, "check"],
            self.settings.command_timeout,
            cwd=config_path.parent,
        )
        if check_result.returncode != 0:
            shutil.copy2(backup_path, config_path)
            detail = check_result.stderr.strip() or check_result.stdout.strip() or "sing-box check 执行失败"
            raise NativeSwitchError(f"配置检查失败: {detail}")

        restart_result = self.runner(
            ["systemctl", "restart", self.settings.singbox_service_name],
            self.settings.command_timeout,
        )
        if restart_result.returncode != 0:
            detail = restart_result.stderr.strip() or restart_result.stdout.strip() or "systemctl restart 执行失败"
            raise NativeSwitchError(f"重启服务失败: {detail}")

        service_status = self._run_text_command(
            ["systemctl", "--no-pager", "--full", "status", self.settings.singbox_service_name]
        )
        recent_logs = self._run_text_command(
            ["journalctl", "-u", self.settings.singbox_service_name, "-n", "8", "--no-pager"]
        )
        current_ip = read_direct_bind_address(config_path)
        public_ipv4 = None
        public_ipv4_updated_at = None
        public_ipv4_error = None

        try:
            public_ip_entry = self.public_ip_service.refresh_cache(target_ip)
        except Exception as exc:
            public_ipv4_error = f"公网 IPv4 刷新失败: {exc}"
        else:
            public_ipv4 = public_ip_entry.public_ipv4
            public_ipv4_updated_at = public_ip_entry.updated_at
            public_ipv4_error = public_ip_entry.error

        return NativeSwitchOutcome(
            target_ip=target_ip,
            backup_path=backup_path,
            current_ip=current_ip,
            public_ipv4=public_ipv4,
            public_ipv4_updated_at=public_ipv4_updated_at,
            public_ipv4_error=public_ipv4_error,
            service_status=service_status,
            recent_logs=recent_logs,
        )

    def ensure_target_ip_is_bound(self, target_ip: str) -> None:
        addresses = list_interface_ipv4_addresses(
            self.settings.interface,
            self.settings.command_timeout,
            runner=self.runner,
        )
        if target_ip not in addresses:
            joined = "\n".join(f"  - {address}" for address in addresses) or "  <空>"
            raise NativeSwitchError(
                f"{target_ip} 没有绑定在接口 {self.settings.interface} 上\n当前 {self.settings.interface} 上的 IPv4:\n{joined}"
            )

    def _run_text_command(self, command: list[str]) -> str:
        result = self.runner(command, self.settings.command_timeout)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
            raise NativeSwitchError(f"{' '.join(command)} 执行失败: {detail}")
        return result.stdout.strip()
