from pathlib import Path

import pytest

from app.config import Settings
from app.services.ip_usage_service import IpUsageError, IpUsageService, IpUsageWindow


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
        helper_path=tmp_path / "helper.sh",
        command_timeout=5,
        debug=False,
        usage_history_path=tmp_path / "ip-usage-history.txt",
    )


def test_ip_usage_service_marks_and_reads_last_used_time(tmp_path: Path):
    service = IpUsageService(build_settings(tmp_path))

    service.mark_used("10.0.0.18", used_at="2026-04-24T01:02:03+00:00")
    service.mark_used("10.0.0.10", used_at="2026-04-23T01:02:03+00:00")

    assert service.read_usage_map() == {
        "10.0.0.10": "2026-04-23T01:02:03+00:00",
        "10.0.0.18": "2026-04-24T01:02:03+00:00",
    }
    assert service.read_usage_windows() == {
        "10.0.0.10": IpUsageWindow(started_at="2026-04-23T01:02:03+00:00", ended_at=None),
        "10.0.0.18": IpUsageWindow(started_at="2026-04-24T01:02:03+00:00", ended_at=None),
    }


def test_ip_usage_service_closes_previous_window_on_switch(tmp_path: Path):
    service = IpUsageService(build_settings(tmp_path))

    service.mark_used("10.0.0.18", used_at="2026-04-24T01:02:03+00:00")
    service.mark_switch("10.0.0.18", "10.0.0.10", switched_at="2026-04-24T03:04:05+00:00")

    assert service.read_usage_windows() == {
        "10.0.0.10": IpUsageWindow(started_at="2026-04-24T03:04:05+00:00", ended_at=None),
        "10.0.0.18": IpUsageWindow(
            started_at="2026-04-24T01:02:03+00:00",
            ended_at="2026-04-24T03:04:05+00:00",
        ),
    }


def test_ip_usage_service_reads_legacy_last_used_records_as_closed_windows(tmp_path: Path):
    settings = build_settings(tmp_path)
    settings.usage_history_path.write_text("10.0.0.18\t2026-04-24T01:02:03+00:00\n", encoding="utf-8")

    assert IpUsageService(settings).read_usage_windows() == {
        "10.0.0.18": IpUsageWindow(
            started_at="2026-04-24T01:02:03+00:00",
            ended_at="2026-04-24T01:02:03+00:00",
        )
    }


def test_ip_usage_service_rejects_invalid_history_line(tmp_path: Path):
    settings = build_settings(tmp_path)
    settings.usage_history_path.write_text("invalid-line\n", encoding="utf-8")

    with pytest.raises(IpUsageError):
        IpUsageService(settings).read_usage_map()
