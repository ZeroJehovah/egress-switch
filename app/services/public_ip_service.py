from __future__ import annotations

import http.client
import ipaddress
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.config import Settings


class PublicIPv4Error(RuntimeError):
    pass


@dataclass(slots=True)
class PublicIPv4CacheEntry:
    bind_ip: str
    public_ipv4: str | None
    updated_at: str
    error: str | None = None


def _default_fetcher(api_url: str, source_ip: str, timeout: int) -> str:
    parsed = urlsplit(api_url)
    if parsed.scheme not in {"http", "https"}:
        raise PublicIPv4Error("公网 IPv4 API 必须使用 http 或 https")

    if not parsed.hostname:
        raise PublicIPv4Error("公网 IPv4 API 缺少主机名")

    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    request_path = parsed.path or "/"
    if parsed.query:
        request_path = f"{request_path}?{parsed.query}"

    connection = connection_cls(
        parsed.hostname,
        port=parsed.port,
        timeout=timeout,
        source_address=(source_ip, 0),
    )

    try:
        connection.request("GET", request_path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        payload = response.read()
    except OSError as exc:
        raise PublicIPv4Error(f"公网 IPv4 查询失败: {exc}") from exc
    finally:
        connection.close()

    if response.status != 200:
        raise PublicIPv4Error(f"公网 IPv4 API 返回异常状态码: {response.status}")

    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicIPv4Error("公网 IPv4 API 返回了无效 JSON") from exc

    ip = data.get("ip")
    if not isinstance(ip, str) or not ip.strip():
        raise PublicIPv4Error("公网 IPv4 API 响应中缺少 ip 字段")

    try:
        return str(ipaddress.IPv4Address(ip))
    except ipaddress.AddressValueError as exc:
        raise PublicIPv4Error(f"公网 IPv4 API 返回了无效 IPv4: {ip}") from exc


class PublicIPv4Service:
    def __init__(self, settings: Settings, fetcher=_default_fetcher) -> None:
        self.settings = settings
        self.fetcher = fetcher

    def refresh_cache(self, bind_ip: str) -> PublicIPv4CacheEntry:
        updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            public_ipv4 = self.fetcher(
                self.settings.public_ip_api_url,
                bind_ip,
                self.settings.command_timeout,
            )
            entry = PublicIPv4CacheEntry(
                bind_ip=bind_ip,
                public_ipv4=public_ipv4,
                updated_at=updated_at,
                error=None,
            )
        except PublicIPv4Error as exc:
            entry = PublicIPv4CacheEntry(
                bind_ip=bind_ip,
                public_ipv4=None,
                updated_at=updated_at,
                error=str(exc),
            )

        self.write_cache(entry)
        return entry

    def read_cache_for_bind_ip(self, bind_ip: str | None) -> PublicIPv4CacheEntry | None:
        if bind_ip is None:
            return None

        entry = self.read_cache()
        if entry is None or entry.bind_ip != bind_ip:
            return None

        return entry

    def read_cache(self) -> PublicIPv4CacheEntry | None:
        cache_path = Path(self.settings.public_ip_cache_path)
        if not cache_path.exists():
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PublicIPv4Error("公网 IPv4 缓存文件不是有效 JSON") from exc

        bind_ip = payload.get("bind_ip")
        updated_at = payload.get("updated_at")
        public_ipv4 = payload.get("public_ipv4")
        error = payload.get("error")

        if not isinstance(bind_ip, str) or not bind_ip:
            raise PublicIPv4Error("公网 IPv4 缓存缺少 bind_ip")
        if not isinstance(updated_at, str) or not updated_at:
            raise PublicIPv4Error("公网 IPv4 缓存缺少 updated_at")
        if public_ipv4 is not None and not isinstance(public_ipv4, str):
            raise PublicIPv4Error("公网 IPv4 缓存中的 public_ipv4 类型无效")
        if error is not None and not isinstance(error, str):
            raise PublicIPv4Error("公网 IPv4 缓存中的 error 类型无效")

        try:
            ipaddress.IPv4Address(bind_ip)
        except ipaddress.AddressValueError as exc:
            raise PublicIPv4Error("公网 IPv4 缓存中的 bind_ip 无效") from exc

        if public_ipv4 is not None:
            try:
                ipaddress.IPv4Address(public_ipv4)
            except ipaddress.AddressValueError as exc:
                raise PublicIPv4Error("公网 IPv4 缓存中的 public_ipv4 无效") from exc

        return PublicIPv4CacheEntry(
            bind_ip=bind_ip,
            public_ipv4=public_ipv4,
            updated_at=updated_at,
            error=error,
        )

    def write_cache(self, entry: PublicIPv4CacheEntry) -> None:
        cache_path = Path(self.settings.public_ip_cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(asdict(entry), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        cache_path.chmod(0o644)
