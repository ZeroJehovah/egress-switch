import json
from pathlib import Path

from app.config import Settings
from app.services.dashboard_service import CandidateIPState, DashboardState
from app.web import create_app, get_next_candidate_ip


class FakeDashboardService:
    def build_state(self):
        return DashboardState(
            current_ip="10.0.0.10",
            public_ipv4="203.0.113.10",
            public_ipv4_updated_at="2026-04-23T10:00:00+00:00",
            public_ipv4_error=None,
            candidate_ips=["10.0.0.10", "10.0.0.11"],
            candidate_items=[
                CandidateIPState(
                    ip="10.0.0.10",
                    last_used_at="2026-04-24T10:00:00+00:00",
                    is_primary=False,
                ),
                CandidateIPState(
                    ip="10.0.0.11",
                    last_used_at="2026-04-23T10:00:00+00:00",
                    is_primary=True,
                ),
            ],
            errors=[],
            interface="enp0s6",
            config_path="/etc/sing-box/config.json",
            primary_ip="10.0.0.11",
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
        public_ip_cache_path=tmp_path / "public-ip-cache.json",
        primary_ip="10.0.0.11",
        usage_history_path=tmp_path / "ip-usage-history.txt",
    )


def write_singbox_config(config_path: Path, bind_ip: str = "10.0.0.10") -> None:
    config_path.write_text(
        json.dumps(
            {
                "outbounds": [
                    {
                        "tag": "direct",
                        "inet4_bind_address": bind_ip,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_public_ip_cache(settings: Settings, bind_ip: str, public_ipv4: str) -> None:
    settings.public_ip_cache_path.write_text(
        json.dumps(
            {
                "bind_ip": bind_ip,
                "public_ipv4": public_ipv4,
                "updated_at": "2026-04-23T10:00:00+00:00",
                "error": None,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_index_page_renders_dashboard(tmp_path: Path):
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=FakeSwitchService())
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "<title>Sing-box Egress Switch</title>" in body
    assert "Sing-box Egress Switch" in body
    assert 'rel="icon"' in body
    assert 'href="/static/favicon.ico?v=' in body
    assert '<img src="/static/favicon.ico?v=' in body
    assert 'href="/static/style.css?v=' in body
    assert 'src="/static/app.js?v=' in body
    assert "服务运行中" in body
    assert "出口 IP 切换面板" in body
    assert "当前状态" in body
    assert "快速操作" in body
    assert "搜索 IP 地址..." in body
    assert "10.0.0.10" in body
    assert "10.0.0.11" in body
    assert "203.0.113.10" in body
    assert "更新时间" in body
    assert "2026-04-23 18:00:00" in body
    assert "最近使用时间" in body
    assert "2026-04-23 18:00:00" in body
    assert "主要 IP" in body
    assert "固定标识" in body
    assert "切换到下一个 IP" in body
    assert "下一个 IP（最长未使用）" in body
    assert "10.0.0.11" in body
    assert 'action="/switch"' in body
    assert 'action="/switch/next"' not in body
    assert "switch-progress" in body
    assert 'data-ajax-switch-form' in body
    assert 'data-ajax-switch-next-form' in body
    assert 'data-ip-search' in body
    assert 'data-refresh-page' in body
    assert 'data-theme-toggle' in body
    assert "切换脚本" not in body
    assert "直接切换到指定地址" not in body
    assert "例如 145 或 10.0.0.145" not in body
    assert "仅供合法用途使用" not in body
    assert "从未切换过" not in body


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


def test_quick_switch_form_posts_rendered_next_ip(tmp_path: Path):
    fake_switch_service = FakeSwitchService()
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()

    response = client.post("/switch", data={"target_ip": "10.0.0.11"}, follow_redirects=True)

    assert response.status_code == 200
    assert fake_switch_service.last_target == "10.0.0.11"
    assert "已切换到 10.0.0.11" in response.get_data(as_text=True)


def test_web_access_whitelist_allows_loopback_without_public_ip_cache(tmp_path: Path):
    app = create_app(build_settings(tmp_path), dashboard_service=FakeDashboardService(), switch_service=FakeSwitchService())
    client = app.test_client()

    response = client.get("/", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})

    assert response.status_code == 200


def test_web_access_whitelist_allows_current_public_ipv4_for_page_static_and_api(tmp_path: Path):
    settings = build_settings(tmp_path)
    write_singbox_config(settings.singbox_config_path, bind_ip="10.0.0.10")
    write_public_ip_cache(settings, bind_ip="10.0.0.10", public_ipv4="203.0.113.10")
    fake_switch_service = FakeSwitchService()
    app = create_app(settings, dashboard_service=FakeDashboardService(), switch_service=fake_switch_service)
    client = app.test_client()
    remote = {"REMOTE_ADDR": "203.0.113.10"}

    page_response = client.get("/", environ_overrides=remote)
    static_response = client.get("/static/app.js?v=1", environ_overrides=remote)
    api_response = client.post("/api/switch", data={"target_ip": "10.0.0.11"}, environ_overrides=remote)

    assert page_response.status_code == 200
    assert static_response.status_code == 200
    assert api_response.status_code == 200
    assert fake_switch_service.last_target == "10.0.0.11"


def test_web_access_whitelist_rejects_non_whitelisted_ip(tmp_path: Path):
    settings = build_settings(tmp_path)
    write_singbox_config(settings.singbox_config_path, bind_ip="10.0.0.10")
    write_public_ip_cache(settings, bind_ip="10.0.0.10", public_ipv4="203.0.113.10")
    app = create_app(settings, dashboard_service=FakeDashboardService(), switch_service=FakeSwitchService())
    client = app.test_client()
    remote = {"REMOTE_ADDR": "203.0.113.11"}

    page_response = client.get("/", environ_overrides=remote)
    static_response = client.get("/static/app.js?v=1", environ_overrides=remote)
    api_response = client.post("/api/switch", data={"target_ip": "10.0.0.11"}, environ_overrides=remote)

    assert page_response.status_code == 403
    assert "访问被拒绝" in page_response.get_data(as_text=True)
    assert static_response.status_code == 403
    assert api_response.status_code == 403
    assert api_response.get_json() == {
        "status": "error",
        "message": "访问被拒绝：当前来源 IP 不在白名单中",
    }


def test_get_next_candidate_ip_wraps_to_first():
    assert get_next_candidate_ip(
        "10.0.0.11",
        [
            CandidateIPState(ip="10.0.0.10", last_used_at="2026-04-23T10:00:00+00:00", is_primary=False),
            CandidateIPState(ip="10.0.0.11", last_used_at="2026-04-24T10:00:00+00:00", is_primary=False),
        ],
    ) == "10.0.0.10"


def test_get_next_candidate_ip_uses_first_when_current_missing():
    assert get_next_candidate_ip(
        None,
        [
            CandidateIPState(ip="10.0.0.10", last_used_at="2026-04-23T10:00:00+00:00", is_primary=False),
            CandidateIPState(ip="10.0.0.11", last_used_at="2026-04-24T10:00:00+00:00", is_primary=False),
        ],
    ) == "10.0.0.10"


def test_get_next_candidate_ip_prefers_never_used_candidates():
    assert get_next_candidate_ip(
        "10.0.0.10",
        [
            CandidateIPState(ip="10.0.0.10", last_used_at="2026-04-24T10:00:00+00:00", is_primary=False),
            CandidateIPState(ip="10.0.0.11", last_used_at=None, is_primary=False),
            CandidateIPState(ip="10.0.0.12", last_used_at=None, is_primary=False),
        ],
        chooser=lambda items: sorted(items)[-1],
    ) == "10.0.0.12"


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
                candidate_items=[],
                errors=[],
                interface="enp0s6",
                config_path="/etc/sing-box/config.json",
                primary_ip="10.0.0.11",
            )

    app = create_app(build_settings(tmp_path), dashboard_service=EmptyDashboardService(), switch_service=FakeSwitchService())
    client = app.test_client()

    response = client.post("/api/switch/next")

    assert response.status_code == 400
    assert response.get_json() == {
        "status": "error",
        "message": "当前没有可切换的候选 IP",
    }
