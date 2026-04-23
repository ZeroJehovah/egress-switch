from __future__ import annotations

import ipaddress
import subprocess
from dataclasses import dataclass

from app.config import Settings
from app.services.native_switcher import list_interface_ipv4_addresses, read_direct_bind_address
from app.services.public_ip_service import PublicIPv4Service


def _default_runner(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


@dataclass(slots=True)
class DashboardState:
    current_ip: str | None
    public_ipv4: str | None
    public_ipv4_updated_at: str | None
    public_ipv4_error: str | None
    candidate_ips: list[str]
    errors: list[str]
    interface: str
    config_path: str


class DashboardService:
    def __init__(self, settings: Settings, runner=_default_runner, public_ip_service: PublicIPv4Service | None = None) -> None:
        self.settings = settings
        self.runner = runner
        self.public_ip_service = public_ip_service or PublicIPv4Service(settings)

    def build_state(self) -> DashboardState:
        errors: list[str] = []

        try:
            current_ip = self.read_current_bind_ip()
        except Exception as exc:
            current_ip = None
            errors.append(f"读取当前绑定 IP 失败: {exc}")

        try:
            candidate_ips = self.list_candidate_ips()
        except Exception as exc:
            candidate_ips = []
            errors.append(f"读取网卡 IP 列表失败: {exc}")

        try:
            public_ip_entry = self.public_ip_service.read_cache_for_bind_ip(current_ip)
        except Exception as exc:
            public_ip_entry = None
            errors.append(f"读取公网 IPv4 缓存失败: {exc}")

        return DashboardState(
            current_ip=current_ip,
            public_ipv4=public_ip_entry.public_ipv4 if public_ip_entry else None,
            public_ipv4_updated_at=public_ip_entry.updated_at if public_ip_entry else None,
            public_ipv4_error=public_ip_entry.error if public_ip_entry else None,
            candidate_ips=candidate_ips,
            errors=errors,
            interface=self.settings.interface,
            config_path=str(self.settings.singbox_config_path),
        )

    def list_candidate_ips(self) -> list[str]:
        addresses = list_interface_ipv4_addresses(
            self.settings.interface,
            self.settings.command_timeout,
            runner=self.runner,
        )

        prefix = f"{self.settings.subnet_prefix}."
        candidates: list[str] = []
        for address in addresses:
            if self.settings.subnet_prefix and not address.startswith(prefix):
                continue
            candidates.append(address)

        return sorted(set(candidates), key=ipaddress.IPv4Address)

    def read_current_bind_ip(self) -> str | None:
        return read_direct_bind_address(self.settings.singbox_config_path)
