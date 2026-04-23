from pathlib import Path

from app.config import Settings
from app.services.dashboard_service import DashboardState
from app.web import create_app, get_next_candidate_ip


class FakeDashboardService:
    def build_state(self):
        return DashboardState(
            current_ip="10.0.0.10",
            public_ipv4="203.0.113.10",
            public_ipv4_updated_at="2026-04-23T10:00:00+00:00",
            public_ipv4_error=None,
            candidate_ips=["10.0.0.10", "10.0.0.11"],
            errors=[],
            interface="enp0s6",
            config_path="/etc/sing-box/config.json",
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
        singbox_bin="sing-box",
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
    assert "203.0.113.10" in body
    assert "更新时间：2026-04-23T10:00:00+00:00" in body
    assert "切换到下一个 IP" in body
    assert "下一个：10.0.0.11" in body
    assert "switch-progress" in body
    assert 'data-ajax-switch-form' in body
    assert 'data-ajax-switch-next-form' in body
    assert "切换脚本" not in body
    assert "直接切换到指定地址" not in body
    assert "例如 145 或 10.0.0.145" not in body


def test_switch_route_redirects_and_flashes(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/switch", data={"target_ip": "10.0.0.11"}, follow_redirects=True)

    assert response.status_code == 200
    assert fake_switch_service.last_target == "10.0.0.11"
    assert "已切换到 10.0.0.11" in response.get_data(as_text=True)


def test_switch_route_rejects_non_candidate_target(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/switch", data={"target_ip": "10.0.0.145"}, follow_redirects=True)

    assert response.status_code == 200
    assert fake_switch_service.last_target is None
    assert "目标 IP 不在当前候选列表中" in response.get_data(as_text=True)


def test_switch_api_returns_json_on_success(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/api/switch", data={"target_ip": "10.0.0.11"})

    assert response.status_code == 200
    assert fake_switch_service.last_target == "10.0.0.11"
    assert response.get_json() == {
        "status": "ok",
        "target_ip": "10.0.0.11",
        "message": "已切换到 10.0.0.11",
    }


def test_switch_api_rejects_non_candidate_target(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/api/switch", data={"target_ip": "10.0.0.145"})

    assert response.status_code == 400
    assert fake_switch_service.last_target is None
    assert response.get_json() == {
        "status": "error",
        "message": "目标 IP 不在当前候选列表中",
    }


def test_switch_next_route_rotates_to_next_candidate(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/switch/next", follow_redirects=True)

    assert response.status_code == 200
    assert fake_switch_service.last_target == "10.0.0.11"
    assert "已轮换到下一个 IP: 10.0.0.11" in response.get_data(as_text=True)


def test_get_next_candidate_ip_wraps_to_first():
    assert get_next_candidate_ip("10.0.0.11", ["10.0.0.10", "10.0.0.11"]) == "10.0.0.10"


def test_get_next_candidate_ip_uses_first_when_current_missing():
    assert get_next_candidate_ip(None, ["10.0.0.10", "10.0.0.11"]) == "10.0.0.10"


def test_switch_next_api_returns_json(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/api/switch/next")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "target_ip": "10.0.0.11",
        "message": "已轮换到下一个 IP: 10.0.0.11",
    }


def test_switch_next_api_returns_error_when_no_candidates(tmp_path: Path):
    class EmptyDashboardService:
        def build_state(self):
            return DashboardState(
                current_ip=None,
                public_ipv4=None,
                public_ipv4_updated_at=None,
                public_ipv4_error=None,
                candidate_ips=[],
                errors=[],
                interface="enp0s6",
                config_path="/etc/sing-box/config.json",
            )

    app = create_app(build_settings(tmp_path), dashboard_service=EmptyDashboardService(), switch_service=FakeSwitchService())
    client = app.test_client()

    response = client.post("/api/switch/next")

    assert response.status_code == 400
    assert response.get_json() == {
        "status": "error",
        "message": "当前没有可切换的候选 IP",
    }
