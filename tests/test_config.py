from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_settings_use_default_primary_ip_when_env_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.BASE_DIR", tmp_path)
    monkeypatch.delenv("SWITCH_IP_PRIMARY_IP", raising=False)

    settings = Settings.from_env()

    assert settings.primary_ip == "10.0.0.18"


def test_settings_use_default_primary_ip_when_env_is_blank(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.config.BASE_DIR", tmp_path)
    monkeypatch.setenv("SWITCH_IP_PRIMARY_IP", "")

    settings = Settings.from_env()

    assert settings.primary_ip == "10.0.0.18"
