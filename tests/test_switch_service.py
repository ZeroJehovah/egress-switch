from pathlib import Path

import pytest

from app.config import Settings
from app.services.helper_client import HelperClient, HelperResult
from app.services.switch_service import SwitchExecutionError, SwitchService, normalize_target_ip


class FakeHelperClient(HelperClient):
    def __init__(self, result: HelperResult):
        self.result = result

    def switch_ip(self, target_ip: str) -> HelperResult:
        self.last_target_ip = target_ip
        return self.result


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
    )


def test_normalize_target_ip_accepts_last_octet():
    assert normalize_target_ip("145", "10.0.0") == "10.0.0.145"


def test_normalize_target_ip_accepts_full_ip():
    assert normalize_target_ip("10.0.0.145", "10.0.0") == "10.0.0.145"


def test_normalize_target_ip_rejects_invalid_ip():
    with pytest.raises(ValueError):
        normalize_target_ip("999.0.0.1", "10.0.0")


def test_switch_service_calls_helper_with_normalized_ip(tmp_path: Path):
    helper = FakeHelperClient(HelperResult(returncode=0, stdout="ok", stderr=""))
    service = SwitchService(build_settings(tmp_path), helper_client=helper)

    assert service.switch_ip("145") == "10.0.0.145"
    assert helper.last_target_ip == "10.0.0.145"


def test_switch_service_raises_on_helper_error(tmp_path: Path):
    helper = FakeHelperClient(HelperResult(returncode=1, stdout="", stderr="boom"))
    service = SwitchService(build_settings(tmp_path), helper_client=helper)

    with pytest.raises(SwitchExecutionError) as exc:
        service.switch_ip("145")

    assert "boom" in str(exc.value)
