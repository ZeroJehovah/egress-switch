from __future__ import annotations

from flask import Flask, current_app, flash, redirect, render_template, request, url_for

from app.config import Settings
from app.services import DashboardService, SwitchExecutionError, SwitchService


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
        return render_template("index.html", state=state, settings=current_app.extensions["settings"])

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
