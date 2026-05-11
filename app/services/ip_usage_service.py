from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings


class IpUsageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IpUsageWindow:
    started_at: str
    ended_at: str | None = None


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


def _normalize_optional_timestamp(raw_value: str | None) -> str | None:
    if raw_value is None or not raw_value.strip():
        return None

    return _normalize_timestamp(raw_value)


class IpUsageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def read_usage_map(self) -> dict[str, str]:
        return {
            ip_address: usage_window.started_at
            for ip_address, usage_window in self.read_usage_windows().items()
        }

    def read_usage_windows(self) -> dict[str, IpUsageWindow]:
        history_path = Path(self.settings.usage_history_path)
        if not history_path.exists():
            return {}

        try:
            raw_lines = history_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise IpUsageError(f"读取最近使用记录文件失败: {history_path}") from exc

        usage_windows: dict[str, IpUsageWindow] = {}
        for line_number, raw_line in enumerate(raw_lines, start=1):
            if not raw_line.strip():
                continue

            line = raw_line.rstrip("\r\n")
            parts = line.split("\t")
            if len(parts) not in {2, 3}:
                raise IpUsageError(f"最近使用记录第 {line_number} 行格式无效")

            started_at = _normalize_timestamp(parts[1])
            ended_at = _normalize_optional_timestamp(parts[2]) if len(parts) == 3 else started_at
            usage_windows[_normalize_ipv4(parts[0])] = IpUsageWindow(
                started_at=started_at,
                ended_at=ended_at,
            )

        return usage_windows

    def mark_used(self, ip_address: str, *, used_at: str | None = None) -> str:
        return self.mark_switch(None, ip_address, switched_at=used_at)

    def mark_switch(
        self,
        previous_ip: str | None,
        target_ip: str,
        *,
        switched_at: str | None = None,
    ) -> str:
        usage_windows = self.read_usage_windows()
        normalized_timestamp = (
            _normalize_timestamp(switched_at)
            if switched_at is not None
            else datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        normalized_target = _normalize_ipv4(target_ip)
        normalized_previous = _normalize_ipv4(previous_ip) if previous_ip else None

        if normalized_previous and normalized_previous != normalized_target:
            previous_window = usage_windows.get(normalized_previous)
            previous_started_at = previous_window.started_at if previous_window else normalized_timestamp
            usage_windows[normalized_previous] = IpUsageWindow(
                started_at=previous_started_at,
                ended_at=normalized_timestamp,
            )

        existing_target_window = usage_windows.get(normalized_target)
        if normalized_previous == normalized_target and existing_target_window and existing_target_window.ended_at is None:
            target_started_at = existing_target_window.started_at
        else:
            target_started_at = normalized_timestamp

        usage_windows[normalized_target] = IpUsageWindow(
            started_at=target_started_at,
            ended_at=None,
        )
        self.write_usage_windows(usage_windows)
        return normalized_timestamp

    def write_usage_map(self, usage_map: dict[str, str]) -> None:
        self.write_usage_windows(
            {
                ip_address: IpUsageWindow(
                    started_at=_normalize_timestamp(timestamp),
                    ended_at=_normalize_timestamp(timestamp),
                )
                for ip_address, timestamp in usage_map.items()
            }
        )

    def write_usage_windows(self, usage_windows: dict[str, IpUsageWindow]) -> None:
        history_path = Path(self.settings.usage_history_path)
        history_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"{ip_address}\t{usage_window.started_at}\t{usage_window.ended_at or ''}"
            for ip_address, usage_window in sorted(
                (
                    (
                        _normalize_ipv4(ip_address),
                        IpUsageWindow(
                            started_at=_normalize_timestamp(usage_window.started_at),
                            ended_at=_normalize_optional_timestamp(usage_window.ended_at),
                        ),
                    )
                    for ip_address, usage_window in usage_windows.items()
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
