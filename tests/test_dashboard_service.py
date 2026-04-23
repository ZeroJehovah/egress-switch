import json
from pathlib import Path
from subprocess import CompletedProcess

from app.config import Settings
from app.services.dashboard_service import DashboardService


def build_settings(tmp_path: Path) -> Settings:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"outbounds": [{"tag": "direct", "inet4_bind_address": "10.0.0.11"}]}), encoding="utf-8")
    return Settings(
        host="127.0.0.1",
        port=8080,
        secret_key="test",
        singbox_config_path=config_path,
        singbox_service_name="sing-box",
        interface="enp0s6",
        subnet_prefix="10.0.0",
        helper_path=tmp_path / "helper.sh",
        command_timeout=5,
        debug=False,
    )


def test_dashboard_reads_current_bind_ip(tmp_path: Path):
    service = DashboardService(build_settings(tmp_path))
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

    service = DashboardService(settings, runner=fake_runner)
    assert service.list_candidate_ips() == ["10.0.0.10", "10.0.0.15"]


def test_dashboard_collects_runtime_errors(tmp_path: Path):
    settings = build_settings(tmp_path)
    settings = Settings(
        host=settings.host,
        port=settings.port,
        secret_key=settings.secret_key,
        singbox_config_path=tmp_path / "missing.json",
        singbox_service_name=settings.singbox_service_name,
        interface=settings.interface,
        subnet_prefix=settings.subnet_prefix,
        helper_path=settings.helper_path,
        command_timeout=settings.command_timeout,
        debug=settings.debug,
    )

    def fake_runner(command, timeout):
        return CompletedProcess(command, 1, stdout="", stderr="device not found")

    state = DashboardService(settings, runner=fake_runner).build_state()
    assert state.current_ip is None
    assert state.candidate_ips == []
    assert len(state.errors) == 2
