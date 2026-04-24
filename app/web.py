from __future__ import annotations

import ipaddress
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, current_app, flash, redirect, render_template, request, url_for
from werkzeug.serving import WSGIRequestHandler
from werkzeug.urls import uri_to_iri

from app.config import Settings
from app.services import CandidateIPState, DashboardService, PublicIPv4Service, SwitchExecutionError, SwitchService
from app.services.native_switcher import read_direct_bind_address

DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
MAX_REQUEST_LOG_TEXT_LENGTH = 240
LAST_USED_TIME_EMPTY_TEXT = "--"
LAST_USED_STATUS_NEVER_LABEL = "从未使用过"


@dataclass(frozen=True, slots=True)
class LastUsedDisplayState:
    text: str
    tone_class: str
    label: str | None = None


def _sanitize_request_log_text(raw_value: str, *, max_length: int = MAX_REQUEST_LOG_TEXT_LENGTH) -> str:
    sanitized_parts: list[str] = []
    for char in raw_value:
        codepoint = ord(char)
        if 32 <= codepoint <= 126:
            sanitized_parts.append(char)
        elif char == "\t":
            sanitized_parts.append("\\t")
        elif char == "\r":
            sanitized_parts.append("\\r")
        elif char == "\n":
            sanitized_parts.append("\\n")
        elif codepoint <= 0xFF:
            sanitized_parts.append(f"\\x{codepoint:02X}")
        elif codepoint <= 0xFFFF:
            sanitized_parts.append(f"\\u{codepoint:04X}")
        else:
            sanitized_parts.append(f"\\U{codepoint:08X}")

    sanitized = "".join(sanitized_parts)
    if len(sanitized) <= max_length:
        return sanitized

    remaining = len(sanitized) - max_length
    return f"{sanitized[:max_length]}...(truncated {remaining} chars)"


class SanitizedWSGIRequestHandler(WSGIRequestHandler):
    def log_error(self, format: str, *args: object) -> None:
        rendered_message = format % args if args else format
        self.log("error", "%s", _sanitize_request_log_text(rendered_message))

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        try:
            path = uri_to_iri(self.path)
            message = f"{self.command} {path} {self.request_version}"
        except AttributeError:
            message = self.requestline

        sanitized_message = _sanitize_request_log_text(message.translate(self._control_char_table))
        self.log("info", '"%s" %s %s', sanitized_message, str(code), size)


def _parse_candidate_last_used_at(raw_value: str) -> datetime:
    parsed = datetime.fromisoformat(raw_value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _describe_last_used(raw_value: str | None, *, now: datetime | None = None) -> LastUsedDisplayState:
    if not raw_value:
        return LastUsedDisplayState(
            text=LAST_USED_TIME_EMPTY_TEXT,
            tone_class="usage-recency-none",
            label=LAST_USED_STATUS_NEVER_LABEL,
        )

    formatted = _format_display_datetime(raw_value) or raw_value

    try:
        parsed = _parse_candidate_last_used_at(raw_value)
    except ValueError:
        return LastUsedDisplayState(
            text=formatted,
            tone_class="usage-recency-none",
            label=LAST_USED_STATUS_NEVER_LABEL,
        )

    reference_time = now or datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    else:
        reference_time = reference_time.astimezone(timezone.utc)

    age = reference_time - parsed.astimezone(timezone.utc)
    if age < timedelta(0):
        age = timedelta(0)

    if age <= timedelta(days=1):
        return LastUsedDisplayState(
            text=formatted,
            tone_class="usage-recency-hot",
            label="1天内使用过",
        )

    if age <= timedelta(days=3):
        return LastUsedDisplayState(
            text=formatted,
            tone_class="usage-recency-warm",
            label="3天内使用过",
        )

    if age <= timedelta(days=7):
        return LastUsedDisplayState(
            text=formatted,
            tone_class="usage-recency-mild",
            label="7天内使用过",
        )

    return LastUsedDisplayState(
        text=formatted,
        tone_class="usage-recency-cool",
        label="7天内未使用过",
    )


def get_next_candidate_ip(
    current_ip: str | None,
    candidate_items: list[CandidateIPState],
    *,
    chooser=random.choice,
) -> str | None:
    if not candidate_items:
        return None

    eligible_items = candidate_items
    if len(candidate_items) > 1 and current_ip is not None:
        eligible_items = [item for item in candidate_items if item.ip != current_ip]

    if not eligible_items:
        return None

    never_used_ips = [item.ip for item in eligible_items if item.last_used_at is None]
    if never_used_ips:
        return chooser(never_used_ips)

    return min(
        eligible_items,
        key=lambda item: (
            _parse_candidate_last_used_at(item.last_used_at or ""),
            ipaddress.IPv4Address(item.ip),
        ),
    ).ip


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
    next_ip = get_next_candidate_ip(state.current_ip, state.candidate_items)
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


def _format_display_datetime(raw_value: str | None) -> str | None:
    if not raw_value:
        return None

    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return raw_value

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def _normalize_client_ip(raw_value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not raw_value:
        return None

    try:
        parsed = ipaddress.ip_address(raw_value)
    except ValueError:
        return None

    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        return parsed.ipv4_mapped

    return parsed


def _read_allowed_public_ipv4() -> str | None:
    settings: Settings = current_app.extensions["settings"]
    public_ip_service: PublicIPv4Service = current_app.extensions["public_ip_service"]

    try:
        current_bind_ip = read_direct_bind_address(settings.singbox_config_path)
    except Exception as exc:
        current_app.logger.warning("读取当前绑定 IP 失败，访问白名单退回为仅本机可用: %s", exc)
        return None

    if current_bind_ip is None:
        return None

    try:
        cache_entry = public_ip_service.read_cache_for_bind_ip(current_bind_ip)
    except Exception as exc:
        current_app.logger.warning("读取公网 IPv4 缓存失败，尝试实时刷新: %s", exc)
        cache_entry = None

    if cache_entry is None or cache_entry.public_ipv4 is None:
        try:
            cache_entry = public_ip_service.refresh_cache(current_bind_ip)
        except Exception as exc:
            current_app.logger.warning("刷新公网 IPv4 失败，访问白名单退回为仅本机可用: %s", exc)
            return None

    return cache_entry.public_ipv4


def _is_request_source_allowed(remote_addr: str | None) -> bool:
    client_ip = _normalize_client_ip(remote_addr)
    if client_ip is None:
        return False

    if client_ip.is_loopback:
        return True

    allowed_public_ipv4 = _read_allowed_public_ipv4()
    if allowed_public_ipv4 is None:
        return False

    allowed_ip = _normalize_client_ip(allowed_public_ipv4)
    return allowed_ip is not None and client_ip == allowed_ip


def _build_forbidden_response() -> tuple[dict[str, str], int] | tuple[str, int, dict[str, str]]:
    message = "访问被拒绝：当前来源 IP 不在白名单中"
    if request.path.startswith("/api/"):
        return {
            "status": "error",
            "message": message,
        }, 403

    return message, 403, {"Content-Type": "text/plain; charset=utf-8"}


def create_app(
    settings: Settings | None = None,
    *,
    dashboard_service: DashboardService | None = None,
    switch_service: SwitchService | None = None,
) -> Flask:
    settings = settings or Settings.from_env()

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = settings.secret_key
    resolved_dashboard_service = dashboard_service or DashboardService(settings)
    app.extensions["settings"] = settings
    app.extensions["dashboard_service"] = resolved_dashboard_service
    app.extensions["switch_service"] = switch_service or SwitchService(settings)
    app.extensions["public_ip_service"] = getattr(resolved_dashboard_service, "public_ip_service", PublicIPv4Service(settings))
    app.add_template_global(_build_static_asset_url, name="static_asset_url")
    app.add_template_global(_describe_last_used, name="describe_last_used")
    app.add_template_global(_format_display_datetime, name="format_display_datetime")

    @app.before_request
    def enforce_web_access_ip_whitelist():
        if _is_request_source_allowed(request.remote_addr):
            return None

        current_app.logger.warning("拒绝来自 %s 的访问请求: %s", request.remote_addr, request.path)
        return _build_forbidden_response()

    @app.get("/")
    def index():
        state = current_app.extensions["dashboard_service"].build_state()
        next_ip = get_next_candidate_ip(state.current_ip, state.candidate_items)
        next_candidate = next((item for item in state.candidate_items if item.ip == next_ip), None)
        next_last_used = _describe_last_used(next_candidate.last_used_at) if next_candidate else None
        return render_template(
            "index.html",
            state=state,
            next_ip=next_ip,
            next_last_used=next_last_used,
            settings=current_app.extensions["settings"],
        )

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
    app.run(
        host=settings.host,
        port=settings.port,
        debug=settings.debug,
        load_dotenv=False,
        request_handler=SanitizedWSGIRequestHandler,
    )


if __name__ == "__main__":
    main()
