from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .env import load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


@dataclass(slots=True)
class Settings:
    host: str
    port: int
    secret_key: str
    singbox_config_path: Path
    singbox_service_name: str
    interface: str
    subnet_prefix: str
    helper_path: Path
    command_timeout: int
    debug: bool

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
            interface=os.getenv("SWITCH_IP_INTERFACE", "enp0s6"),
            subnet_prefix=os.getenv("SWITCH_IP_SUBNET_PREFIX", "10.0.0"),
            helper_path=_resolve_path(
                os.getenv("SWITCH_IP_HELPER_PATH", "scripts/switch-egress-ip.sh"),
                BASE_DIR,
            ),
            command_timeout=int(os.getenv("SWITCH_IP_COMMAND_TIMEOUT", "60")),
            debug=_as_bool(os.getenv("SWITCH_IP_DEBUG"), default=False),
        )
