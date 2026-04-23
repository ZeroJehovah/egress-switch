from __future__ import annotations

import ipaddress

from app.config import Settings
from app.services.helper_client import HelperClient


class SwitchExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        target_ip: str,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.target_ip = target_ip
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def normalize_target_ip(value: str, subnet_prefix: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("目标 IP 不能为空")

    if candidate.isdigit():
        octet = int(candidate)
        if octet < 0 or octet > 255:
            raise ValueError("最后一段必须在 0-255")
        return f"{subnet_prefix}.{octet}"

    try:
        return str(ipaddress.IPv4Address(candidate))
    except ipaddress.AddressValueError as exc:
        raise ValueError("目标 IP 格式不正确") from exc


class SwitchService:
    def __init__(self, settings: Settings, helper_client: HelperClient | None = None) -> None:
        self.settings = settings
        self.helper_client = helper_client or HelperClient(
            helper_path=settings.helper_path,
            timeout=settings.command_timeout,
        )

    def switch_ip(self, target_ip: str) -> str:
        normalized_target = normalize_target_ip(target_ip, self.settings.subnet_prefix)
        result = self.helper_client.switch_ip(normalized_target)
        if result.success:
            return normalized_target

        detail = result.stderr.strip() or result.stdout.strip() or f"helper 返回码 {result.returncode}"
        raise SwitchExecutionError(
            f"切换失败: {detail}",
            normalized_target,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
