from pathlib import Path
from subprocess import CompletedProcess

from app.services.helper_client import HelperClient


def test_helper_client_falls_back_from_sh_to_py(tmp_path: Path):
    helper_py = tmp_path / "switch-egress-ip.py"
    helper_py.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    captured = {}

    def fake_runner(command, timeout):
        captured["command"] = command
        captured["timeout"] = timeout
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    client = HelperClient(tmp_path / "switch-egress-ip.sh", timeout=5, runner=fake_runner)
    result = client.switch_ip("10.0.0.11")

    assert result.success is True
    assert captured["command"] == [str(helper_py), "10.0.0.11"]
    assert captured["timeout"] == 5
