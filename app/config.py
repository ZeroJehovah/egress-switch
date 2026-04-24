from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path

from .env import load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PRIMARY_IP = "10.0.0.18"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _normalize_optional_ipv4(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None

    candidate = raw_value.strip()
    if not candidate:
        return None

    try:
        return str(ipaddress.IPv4Address(candidate))
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"无效的 IPv4 地址配置: {candidate}") from exc


@dataclass(slots=True)
class Settings:
    host: str
    port: int
    secret_key: str
    singbox_config_path: Path
    singbox_service_name: str
    singbox_bin: str
    interface: str
    subnet_prefix: str
    helper_path: Path
    command_timeout: int
    debug: bool
    public_ip_api_url: str = "https://api.ipify.org?format=json"
    public_ip_cache_path: Path = BASE_DIR / ".run/public-ip-cache.json"
    primary_ip: str | None = DEFAULT_PRIMARY_IP
    usage_history_path: Path = BASE_DIR / ".run/ip-usage-history.txt"

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file(BASE_DIR / ".env")
        return cls(
            host=os.getenv("SWITCH_IP_HOST", "0.0.0.0"),
            port=int(os.getenv("SWITCH_IP_PORT", "8080")),
            secret_key=os.getenv("SWITCH_IP_SECRET_KEY", "change-me"),
            singbox_config_path=_resolve_path(
                os.getenv("SINGBOX_CONFIG_PATH", "/etc/sing-box/config.json"),
                BASE_DIR,
            ),
            singbox_service_name=os.getenv("SINGBOX_SERVICE_NAME", "sing-box"),
            singbox_bin=os.getenv("SINGBOX_BIN", "sing-box"),
            interface=os.getenv("SWITCH_IP_INTERFACE", "enp0s6"),
            subnet_prefix=os.getenv("SWITCH_IP_SUBNET_PREFIX", "10.0.0"),
            helper_path=_resolve_path(
                os.getenv("SWITCH_IP_HELPER_PATH", "scripts/switch-egress-ip.py"),
                BASE_DIR,
            ),
            command_timeout=int(os.getenv("SWITCH_IP_COMMAND_TIMEOUT", "60")),
            debug=_as_bool(os.getenv("SWITCH_IP_DEBUG"), default=False),
            public_ip_api_url=os.getenv("SWITCH_IP_PUBLIC_IP_API_URL", "https://api.ipify.org?format=json"),
            public_ip_cache_path=_resolve_path(
                os.getenv("SWITCH_IP_PUBLIC_IP_CACHE_PATH", ".run/public-ip-cache.json"),
                BASE_DIR,
            ),
            primary_ip=_normalize_optional_ipv4(os.getenv("SWITCH_IP_PRIMARY_IP") or DEFAULT_PRIMARY_IP),
            usage_history_path=_resolve_path(
                os.getenv("SWITCH_IP_USAGE_HISTORY_PATH", ".run/ip-usage-history.txt"),
                BASE_DIR,
            ),
        )
