#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.env import load_env_file


def build_api_base_url() -> str:
    load_env_file(ROOT_DIR / ".env")

    explicit_base_url = os.getenv("SWITCH_IP_API_BASE_URL")
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    port = os.getenv("SWITCH_IP_PORT", "8080")
    return f"http://127.0.0.1:{port}"


def parse_payload(raw_body: bytes) -> dict:
    if not raw_body:
        return {}
    return json.loads(raw_body.decode("utf-8"))


def main() -> int:
    url = f"{build_api_base_url()}/api/switch/next"
    timeout = int(os.getenv("SWITCH_IP_COMMAND_TIMEOUT", "60"))
    request = urllib.request.Request(
        url,
        data=b"",
        method="POST",
        headers={"Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = parse_payload(response.read())
    except urllib.error.HTTPError as exc:
        payload = parse_payload(exc.read())
        message = payload.get("message") or f"请求失败，HTTP {exc.code}"
        print(message, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"无法连接 switch-ip API: {exc.reason}", file=sys.stderr)
        return 1

    message = payload.get("message", "切换完成")
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
