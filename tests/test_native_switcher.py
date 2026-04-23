import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.config import Settings
from app.services.native_switcher import NativeSwitchError, NativeSwitcher


def build_settings(tmp_path: Path) -> Settings:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"outbounds": [{"tag": "direct", "inet4_bind_address": "10.0.0.10"}]}),
        encoding="utf-8",
    )
    return Settings(
        host="127.0.0.1",
        port=8080,
        secret_key="test",
        singbox_config_path=config_path,
        singbox_service_name="sing-box",
        singbox_bin="sing-box",
        interface="enp0s6",
        subnet_prefix="10.0.0",
        helper_path=tmp_path / "scripts" / "switch-egress-ip.py",
        command_timeout=5,
        debug=False,
    )


def test_native_switcher_updates_config_and_returns_logs(tmp_path: Path):
    settings = build_settings(tmp_path)

    def fake_runner(command, timeout, cwd=None):
        if command[:4] == ["ip", "-o", "-4", "addr"]:
            return CompletedProcess(
                command,
                0,
                stdout="2: enp0s6    inet 10.0.0.10/24 brd 10.0.0.255 scope global enp0s6\n"
                "2: enp0s6    inet 10.0.0.11/24 brd 10.0.0.255 scope global secondary enp0s6\n",
                stderr="",
            )
        if command == ["sing-box", "check"]:
            assert cwd == settings.singbox_config_path.parent
            return CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["systemctl", "restart", "sing-box"]:
            return CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["systemctl", "--no-pager", "--full", "status", "sing-box"]:
            return CompletedProcess(command, 0, stdout="active (running)", stderr="")
        if command == ["journalctl", "-u", "sing-box", "-n", "8", "--no-pager"]:
            return CompletedProcess(command, 0, stdout="recent logs", stderr="")
        raise AssertionError(command)

    outcome = NativeSwitcher(settings, runner=fake_runner).switch_ip("10.0.0.11")

    assert outcome.target_ip == "10.0.0.11"
    assert outcome.current_ip == "10.0.0.11"
    assert outcome.service_status == "active (running)"
    assert outcome.recent_logs == "recent logs"
    assert settings.singbox_config_path.exists()
    assert "10.0.0.11" in settings.singbox_config_path.read_text(encoding="utf-8")
    backups = list(tmp_path.glob("config.json.bak.*"))
    assert len(backups) == 1


def test_native_switcher_rolls_back_on_check_failure(tmp_path: Path):
    settings = build_settings(tmp_path)
    original = settings.singbox_config_path.read_text(encoding="utf-8")

    def fake_runner(command, timeout, cwd=None):
        if command[:4] == ["ip", "-o", "-4", "addr"]:
            return CompletedProcess(
                command,
                0,
                stdout="2: enp0s6    inet 10.0.0.11/24 brd 10.0.0.255 scope global secondary enp0s6\n",
                stderr="",
            )
        if command == ["sing-box", "check"]:
            return CompletedProcess(command, 1, stdout="", stderr="invalid config")
        raise AssertionError(command)

    with pytest.raises(NativeSwitchError) as exc:
        NativeSwitcher(settings, runner=fake_runner).switch_ip("10.0.0.11")

    assert "配置检查失败" in str(exc.value)
    assert settings.singbox_config_path.read_text(encoding="utf-8") == original


def test_native_switcher_rejects_unbound_ip(tmp_path: Path):
    settings = build_settings(tmp_path)

    def fake_runner(command, timeout, cwd=None):
        if command[:4] == ["ip", "-o", "-4", "addr"]:
            return CompletedProcess(
                command,
                0,
                stdout="2: enp0s6    inet 10.0.0.10/24 brd 10.0.0.255 scope global enp0s6\n",
                stderr="",
            )
        raise AssertionError(command)

    with pytest.raises(NativeSwitchError) as exc:
        NativeSwitcher(settings, runner=fake_runner).switch_ip("10.0.0.88")

    assert "没有绑定在接口 enp0s6 上" in str(exc.value)
