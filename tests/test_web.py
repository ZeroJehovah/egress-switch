from pathlib import Path

from app.config import Settings
from app.services.dashboard_service import DashboardState
from app.web import create_app


class FakeDashboardService:
    def build_state(self):
        return DashboardState(
            current_ip="10.0.0.10",
            candidate_ips=["10.0.0.10", "10.0.0.11"],
            errors=[],
            interface="enp0s6",
            config_path="/etc/sing-box/config.json",
            helper_path="/opt/helper.sh",
        )


class FakeSwitchService:
    def __init__(self):
        self.last_target = None

    def switch_ip(self, target_ip: str) -> str:
        self.last_target = target_ip
        return "10.0.0.11"


def build_settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8080,
        secret_key="test",
        singbox_config_path=tmp_path / "config.json",
        singbox_service_name="sing-box",
        interface="enp0s6",
        subnet_prefix="10.0.0",
        helper_path=tmp_path / "helper.sh",
        command_timeout=5,
        debug=False,
    )


def test_index_page_renders_dashboard(tmp_path: Path):
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=FakeSwitchService())
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "出口 IP 切换面板" in body
    assert "10.0.0.10" in body
    assert "10.0.0.11" in body


def test_switch_route_redirects_and_flashes(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/switch", data={"target_ip": "10.0.0.11"}, follow_redirects=True)

    assert response.status_code == 200
    assert fake_switch_service.last_target == "10.0.0.11"
    assert "已切换到 10.0.0.11" in response.get_data(as_text=True)
