from __future__ import annotations

from pathlib import Path

from flask import Flask, current_app, flash, redirect, render_template, request, url_for

from app.config import Settings
from app.services import DashboardService, SwitchExecutionError, SwitchService


def get_next_candidate_ip(current_ip: str | None, candidate_ips: list[str]) -> str | None:
    if not candidate_ips:
        return None

    if current_ip not in candidate_ips:
        return candidate_ips[0]

    current_index = candidate_ips.index(current_ip)
    next_index = (current_index + 1) % len(candidate_ips)
    return candidate_ips[next_index]


def _switch_to_target(target_ip: str) -> tuple[bool, str, str | None]:
    try:
        normalized_target = current_app.extensions["switch_service"].switch_ip(target_ip)
    except ValueError as exc:
        return False, str(exc), None
    except FileNotFoundError as exc:
        return False, str(exc), None
    except SwitchExecutionError as exc:
        return False, str(exc), None

    return True, "", normalized_target


def _switch_to_next_candidate() -> tuple[bool, str, str | None]:
    state = current_app.extensions["dashboard_service"].build_state()
    next_ip = get_next_candidate_ip(state.current_ip, state.candidate_ips)
    if next_ip is None:
        return False, "当前没有可切换的候选 IP", None

    return _switch_to_target(next_ip)


def _get_requested_target_ip() -> str:
    if request.form:
        return request.form.get("target_ip", "")

    payload = request.get_json(silent=True) or {}
    return payload.get("target_ip", "")


def _build_static_asset_url(filename: str) -> str:
    static_folder = current_app.static_folder
    if not static_folder:
        return url_for("static", filename=filename)

    asset_path = Path(static_folder, filename)
    if not asset_path.is_file():
        return url_for("static", filename=filename)

    return url_for("static", filename=filename, v=asset_path.stat().st_mtime_ns)


def create_app(
    settings: Settings | None = None,
    *,
    dashboard_service: DashboardService | None = None,
    switch_service: SwitchService | None = None,
) -> Flask:
    settings = settings or Settings.from_env()

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = settings.secret_key
    app.extensions["settings"] = settings
    app.extensions["dashboard_service"] = dashboard_service or DashboardService(settings)
    app.extensions["switch_service"] = switch_service or SwitchService(settings)
    app.add_template_global(_build_static_asset_url, name="static_asset_url")

    @app.get("/")
    def index():
        state = current_app.extensions["dashboard_service"].build_state()
        next_ip = get_next_candidate_ip(state.current_ip, state.candidate_ips)
        return render_template("index.html", state=state, next_ip=next_ip, settings=current_app.extensions["settings"])

    @app.post("/switch")
    def switch_ip():
        target_ip = _get_requested_target_ip()
        state = current_app.extensions["dashboard_service"].build_state()
        if target_ip not in state.candidate_ips:
            flash("目标 IP 不在当前候选列表中", "error")
            return redirect(url_for("index"))

        success, message, normalized_target = _switch_to_target(target_ip)
        if success:
            flash(f"已切换到 {normalized_target}", "success")
        else:
            flash(message, "error")

        return redirect(url_for("index"))

    @app.post("/api/switch")
    def switch_ip_api():
        target_ip = _get_requested_target_ip()
        state = current_app.extensions["dashboard_service"].build_state()
        if target_ip not in state.candidate_ips:
            return {
                "status": "error",
                "message": "目标 IP 不在当前候选列表中",
            }, 400

        success, message, normalized_target = _switch_to_target(target_ip)
        if success:
            return {
                "status": "ok",
                "target_ip": normalized_target,
                "message": f"已切换到 {normalized_target}",
            }

        return {
            "status": "error",
            "message": message,
        }, 400

    @app.post("/switch/next")
    def switch_next_ip():
        success, message, normalized_target = _switch_to_next_candidate()
        if success:
            flash(f"已轮换到下一个 IP: {normalized_target}", "success")
        else:
            flash(message, "error")

        return redirect(url_for("index"))

    @app.post("/api/switch/next")
    def switch_next_ip_api():
        success, message, normalized_target = _switch_to_next_candidate()
        if success:
            return {
                "status": "ok",
                "target_ip": normalized_target,
                "message": f"已轮换到下一个 IP: {normalized_target}",
            }

        return {
            "status": "error",
            "message": message,
        }, 400

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


def main() -> None:
    app = create_app()
    settings: Settings = app.extensions["settings"]
    app.run(host=settings.host, port=settings.port, debug=settings.debug, load_dotenv=False)


if __name__ == "__main__":
    main()
