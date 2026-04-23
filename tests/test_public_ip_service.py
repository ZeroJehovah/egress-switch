import json
from pathlib import Path

import pytest

from app.config import Settings
from app.services.public_ip_service import PublicIPv4Error, PublicIPv4Service


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        secret_key="test",
        singbox_config_path=tmp_path / "config.json",
        singbox_service_name="sing-box",
        singbox_bin="sing-box",
        interface="enp0s6",
        subnet_prefix="10.0.0",
        helper_path=tmp_path / "helper.py",
        command_timeout=5,
        debug=False,
        public_ip_api_url="https://api.ipify.org?format=json",
        public_ip_cache_path=tmp_path / "public-ip-cache.json",
    )


def test_public_ip_service_refreshes_cache(tmp_path: Path):
    settings = build_settings(tmp_path)

    def fake_fetcher(api_url, source_ip, timeout):
        assert api_url == "https://api.ipify.org?format=json"
        assert source_ip == "10.0.0.11"
        assert timeout == 5
        return "203.0.113.11"

    service = PublicIPv4Service(settings, fetcher=fake_fetcher)
    entry = service.refresh_cache("10.0.0.11")

    assert entry.bind_ip == "10.0.0.11"
    assert entry.public_ipv4 == "203.0.113.11"
    assert entry.error is None
    payload = json.loads(settings.public_ip_cache_path.read_text(encoding="utf-8"))
    assert payload["public_ipv4"] == "203.0.113.11"


def test_public_ip_service_caches_fetch_error(tmp_path: Path):
    settings = build_settings(tmp_path)

    def fake_fetcher(api_url, source_ip, timeout):
        raise PublicIPv4Error("network down")

    service = PublicIPv4Service(settings, fetcher=fake_fetcher)
    entry = service.refresh_cache("10.0.0.11")

    assert entry.bind_ip == "10.0.0.11"
    assert entry.public_ipv4 is None
    assert entry.error == "network down"


def test_public_ip_service_reads_cache_for_current_bind_ip(tmp_path: Path):
    settings = build_settings(tmp_path)
    settings.public_ip_cache_path.write_text(
        json.dumps(
            {
                "bind_ip": "10.0.0.11",
                "public_ipv4": "203.0.113.11",
                "updated_at": "2026-04-23T10:00:00+00:00",
                "error": None,
            }
        ),
        encoding="utf-8",
    )

    entry = PublicIPv4Service(settings).read_cache_for_bind_ip("10.0.0.11")

    assert entry is not None
    assert entry.public_ipv4 == "203.0.113.11"


def test_public_ip_service_rejects_invalid_cache(tmp_path: Path):
    settings = build_settings(tmp_path)
    settings.public_ip_cache_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(PublicIPv4Error):
        PublicIPv4Service(settings).read_cache()
