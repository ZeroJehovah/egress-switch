import json
from pathlib import Path
from subprocess import CompletedProcess

from app.config import Settings
from app.services.dashboard_service import DashboardService
from app.services.ip_usage_service import IpUsageWindow
from app.services.public_ip_service import PublicIPv4CacheEntry


class FakePublicIPService:
    def __init__(self, entry: PublicIPv4CacheEntry | None = None):
        self.entry = entry

    def read_cache_for_bind_ip(self, bind_ip: str | None):
        if self.entry is None or bind_ip != self.entry.bind_ip:
            return None
        return self.entry


class FakeIpUsageService:
    def __init__(self, usage_windows: dict[str, IpUsageWindow] | None = None):
        self.usage_windows = usage_windows or {}

    def read_usage_windows(self) -> dict[str, IpUsageWindow]:
        return self.usage_windows


def build_settings(tmp_path: Path) -> Settings:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"outbounds": [{"tag": "direct", "inet4_bind_address": "10.0.0.11"}]}), encoding="utf-8")
    return Settings(
        host="127.0.0.1",
        port=8080,
        secret_key="test",
        singbox_config_path=config_path,
        singbox_service_name="sing-box",
        singbox_bin="sing-box",
        interface="enp0s6",
        subnet_prefix="10.0.0",
        helper_path=tmp_path / "helper.sh",
        command_timeout=5,
        debug=False,
        primary_ip="10.0.0.18",
        usage_history_path=tmp_path / "ip-usage-history.txt",
    )


def test_dashboard_reads_current_bind_ip(tmp_path: Path):
    service = DashboardService(
        build_settings(tmp_path),
        public_ip_service=FakePublicIPService(),
        ip_usage_service=FakeIpUsageService(),
    )
    assert service.read_current_bind_ip() == "10.0.0.11"


def test_dashboard_lists_candidate_ips(tmp_path: Path):
    settings = build_settings(tmp_path)

    def fake_runner(command, timeout):
        assert command == ["ip", "-o", "-4", "addr", "show", "dev", "enp0s6"]
        assert timeout == 5
        return CompletedProcess(
            command,
            0,
            stdout=(
                "2: enp0s6    inet 10.0.0.10/24 brd 10.0.0.255 scope global enp0s6\n"
                "2: enp0s6    inet 10.0.0.15/24 brd 10.0.0.255 scope global secondary enp0s6\n"
                "2: enp0s6    inet 192.168.1.2/24 brd 192.168.1.255 scope global secondary enp0s6\n"
            ),
            stderr="",
        )

    service = DashboardService(
        settings,
        runner=fake_runner,
        public_ip_service=FakePublicIPService(),
        ip_usage_service=FakeIpUsageService(),
    )
    assert service.list_candidate_ips() == ["10.0.0.10", "10.0.0.15"]


def test_dashboard_collects_runtime_errors(tmp_path: Path):
    settings = build_settings(tmp_path)
    settings = Settings(
        host=settings.host,
        port=settings.port,
        secret_key=settings.secret_key,
        singbox_config_path=tmp_path / "missing.json",
        singbox_service_name=settings.singbox_service_name,
        singbox_bin=settings.singbox_bin,
        interface=settings.interface,
        subnet_prefix=settings.subnet_prefix,
        helper_path=settings.helper_path,
        command_timeout=settings.command_timeout,
        debug=settings.debug,
    )

    def fake_runner(command, timeout):
        return CompletedProcess(command, 1, stdout="", stderr="device not found")

    state = DashboardService(
        settings,
        runner=fake_runner,
        public_ip_service=FakePublicIPService(),
        ip_usage_service=FakeIpUsageService(),
    ).build_state()
    assert state.current_ip is None
    assert state.candidate_ips == []
    assert state.candidate_items == []
    assert len(state.errors) == 2


def test_dashboard_reads_cached_public_ipv4(tmp_path: Path):
    service = DashboardService(
        build_settings(tmp_path),
        public_ip_service=FakePublicIPService(
            PublicIPv4CacheEntry(
                bind_ip="10.0.0.11",
                public_ipv4="203.0.113.11",
                updated_at="2026-04-23T10:00:00+00:00",
                error=None,
            )
        ),
        ip_usage_service=FakeIpUsageService(),
    )

    state = service.build_state()

    assert state.public_ipv4 == "203.0.113.11"
    assert state.public_ipv4_error is None


def test_dashboard_includes_last_used_and_primary_markers(tmp_path: Path):
    settings = build_settings(tmp_path)

    def fake_runner(command, timeout):
        return CompletedProcess(
            command,
            0,
            stdout=(
                "2: enp0s6    inet 10.0.0.11/24 brd 10.0.0.255 scope global enp0s6\n"
                "2: enp0s6    inet 10.0.0.18/24 brd 10.0.0.255 scope global secondary enp0s6\n"
            ),
            stderr="",
        )

    service = DashboardService(
        settings,
        runner=fake_runner,
        public_ip_service=FakePublicIPService(),
        ip_usage_service=FakeIpUsageService(
            {
                "10.0.0.18": IpUsageWindow(
                    started_at="2026-04-24T02:03:04+00:00",
                    ended_at="2026-04-24T03:04:05+00:00",
                )
            }
        ),
    )

    state = service.build_state()

    assert state.primary_ip == "10.0.0.18"
    assert [(item.ip, item.usage_started_at, item.usage_ended_at, item.is_primary) for item in state.candidate_items] == [
        ("10.0.0.11", None, None, False),
        ("10.0.0.18", "2026-04-24T02:03:04+00:00", "2026-04-24T03:04:05+00:00", True),
    ]
