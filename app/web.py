from __future__ import annotations

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

    @app.get("/")
    def index():
        state = current_app.extensions["dashboard_service"].build_state()
        next_ip = get_next_candidate_ip(state.current_ip, state.candidate_ips)
        return render_template("index.html", state=state, next_ip=next_ip, settings=current_app.extensions["settings"])

    @app.post("/switch")
    def switch_ip():
        target_ip = request.form.get("target_ip", "")
        state = current_app.extensions["dashboard_service"].build_state()
        if target_ip not in state.candidate_ips:
            flash("目标 IP 不在当前候选列表中", "error")
            return redirect(url_for("index"))

        try:
            normalized_target = current_app.extensions["switch_service"].switch_ip(target_ip)
        except ValueError as exc:
            flash(str(exc), "error")
        except FileNotFoundError as exc:
            flash(str(exc), "error")
        except SwitchExecutionError as exc:
            flash(str(exc), "error")
        else:
            flash(f"已切换到 {normalized_target}", "success")

        return redirect(url_for("index"))

    @app.post("/switch/next")
    def switch_next_ip():
        state = current_app.extensions["dashboard_service"].build_state()
        next_ip = get_next_candidate_ip(state.current_ip, state.candidate_ips)
        if next_ip is None:
            flash("当前没有可切换的候选 IP", "error")
            return redirect(url_for("index"))

        try:
            normalized_target = current_app.extensions["switch_service"].switch_ip(next_ip)
        except ValueError as exc:
            flash(str(exc), "error")
        except FileNotFoundError as exc:
            flash(str(exc), "error")
        except SwitchExecutionError as exc:
            flash(str(exc), "error")
        else:
            flash(f"已轮换到下一个 IP: {normalized_target}", "success")

        return redirect(url_for("index"))

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
