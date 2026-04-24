from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings


class IpUsageError(RuntimeError):
    pass


def _normalize_ipv4(raw_value: str) -> str:
    candidate = raw_value.strip()
    if not candidate:
        raise IpUsageError("最近使用记录中的 IP 不能为空")

    try:
        return str(ipaddress.IPv4Address(candidate))
    except ipaddress.AddressValueError as exc:
        raise IpUsageError(f"最近使用记录中的 IP 无效: {candidate}") from exc


def _normalize_timestamp(raw_value: str) -> str:
    candidate = raw_value.strip()
    if not candidate:
        raise IpUsageError("最近使用记录中的时间不能为空")

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise IpUsageError(f"最近使用记录中的时间格式无效: {candidate}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.isoformat(timespec="seconds")


class IpUsageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def read_usage_map(self) -> dict[str, str]:
        history_path = Path(self.settings.usage_history_path)
        if not history_path.exists():
            return {}

        try:
            raw_lines = history_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise IpUsageError(f"读取最近使用记录文件失败: {history_path}") from exc

        usage_map: dict[str, str] = {}
        for line_number, raw_line in enumerate(raw_lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            ip_value, separator, timestamp_value = line.partition("\t")
            if not separator:
                raise IpUsageError(f"最近使用记录第 {line_number} 行格式无效")

            usage_map[_normalize_ipv4(ip_value)] = _normalize_timestamp(timestamp_value)

        return usage_map

    def mark_used(self, ip_address: str, *, used_at: str | None = None) -> str:
        usage_map = self.read_usage_map()
        normalized_ip = _normalize_ipv4(ip_address)
        normalized_timestamp = (
            _normalize_timestamp(used_at)
            if used_at is not None
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )

        usage_map[normalized_ip] = normalized_timestamp
        self.write_usage_map(usage_map)
        return normalized_timestamp

    def write_usage_map(self, usage_map: dict[str, str]) -> None:
        history_path = Path(self.settings.usage_history_path)
        history_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"{ip_address}\t{timestamp}"
            for ip_address, timestamp in sorted(
                (
                    (_normalize_ipv4(ip_address), _normalize_timestamp(timestamp))
                    for ip_address, timestamp in usage_map.items()
                ),
                key=lambda item: ipaddress.IPv4Address(item[0]),
            )
        ]

        content = "\n".join(lines)
        if content:
            content = f"{content}\n"

        try:
            history_path.write_text(content, encoding="utf-8")
            history_path.chmod(0o644)
        except OSError as exc:
            raise IpUsageError(f"写入最近使用记录文件失败: {history_path}") from exc
