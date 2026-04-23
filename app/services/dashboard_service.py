from __future__ import annotations

import ipaddress
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings


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
    candidate_ips: list[str]
    errors: list[str]
    interface: str
    config_path: str
    helper_path: str


class DashboardService:
    def __init__(self, settings: Settings, runner=_default_runner) -> None:
        self.settings = settings
        self.runner = runner

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

        return DashboardState(
            current_ip=current_ip,
            candidate_ips=candidate_ips,
            errors=errors,
            interface=self.settings.interface,
            config_path=str(self.settings.singbox_config_path),
            helper_path=str(self.settings.helper_path),
        )

    def list_candidate_ips(self) -> list[str]:
        result = self.runner(
            ["ip", "-o", "-4", "addr", "show", "dev", self.settings.interface],
            timeout=self.settings.command_timeout,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
            raise RuntimeError(detail)

        prefix = f"{self.settings.subnet_prefix}."
        candidates: list[str] = []
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue

            address = parts[3].split("/", 1)[0]
            try:
                ipaddress.IPv4Address(address)
            except ValueError:
                continue

            if self.settings.subnet_prefix and not address.startswith(prefix):
                continue
            candidates.append(address)

        return sorted(set(candidates), key=ipaddress.IPv4Address)

    def read_current_bind_ip(self) -> str | None:
        config_path = Path(self.settings.singbox_config_path)
        data = json.loads(config_path.read_text(encoding="utf-8"))

        for outbound in data.get("outbounds", []):
            if outbound.get("tag") == "direct":
                value = outbound.get("inet4_bind_address")
                return str(value) if value else None

        raise RuntimeError("没有找到 tag 为 direct 的 outbound")
