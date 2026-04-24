from __future__ import annotations

import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def copy_runtime_scripts(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(parents=True)

    for name in ("start.sh", "stop.sh", "restart.sh", "update.sh"):
        source = ROOT_DIR / "scripts" / name
        target = scripts_dir / name
        shutil.copy2(source, target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR)

    (repo_root / ".env").write_text("SWITCH_IP_SYSTEMD_SERVICE_NAME=switch-ip\n", encoding="utf-8")
    return repo_root


def write_fake_bin(bin_dir: Path, name: str, content: str) -> None:
    target = bin_dir / name
    target.write_text(content, encoding="utf-8")
    target.chmod(0o755)


def test_start_script_exits_early_when_systemd_service_is_active(tmp_path: Path) -> None:
    repo_root = copy_runtime_scripts(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl_log = tmp_path / "systemctl.log"

    write_fake_bin(
        fake_bin,
        "systemctl",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "$*" >> "${FAKE_SYSTEMCTL_LOG}"
            if [[ "$1" == "show" ]]; then
              printf 'loaded\\n'
              exit 0
            fi
            if [[ "$1" == "is-active" && "$2" == "--quiet" ]]; then
              exit 0
            fi
            exit 0
            """
        ),
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "FAKE_SYSTEMCTL_LOG": str(systemctl_log),
            "PYTHON_BIN": "/definitely-missing-python",
        }
    )

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "start.sh")],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "switch-ip 已由 systemd 管理并运行" in result.stdout
    assert not (repo_root / ".venv").exists()

    systemctl_calls = systemctl_log.read_text(encoding="utf-8")
    assert "show --property=LoadState --value switch-ip" in systemctl_calls
    assert "is-active --quiet switch-ip" in systemctl_calls


def test_update_script_uses_systemd_restart_for_active_service(tmp_path: Path) -> None:
    repo_root = copy_runtime_scripts(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl_log = tmp_path / "systemctl.log"
    git_log = tmp_path / "git.log"

    write_fake_bin(
        fake_bin,
        "systemctl",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "$*" >> "${FAKE_SYSTEMCTL_LOG}"
            if [[ "$1" == "show" ]]; then
              printf 'loaded\\n'
              exit 0
            fi
            if [[ "$1" == "is-active" && "$2" == "--quiet" ]]; then
              exit 0
            fi
            if [[ "$1" == "restart" ]]; then
              exit 0
            fi
            printf 'unexpected systemctl call: %s\\n' "$*" >&2
            exit 1
            """
        ),
    )
    write_fake_bin(
        fake_bin,
        "git",
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "$*" >> "${FAKE_GIT_LOG}"
            if [[ "$1" == "diff" || "$1" == "pull" ]]; then
              exit 0
            fi
            printf 'unexpected git call: %s\\n' "$*" >&2
            exit 1
            """
        ),
    )

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "FAKE_SYSTEMCTL_LOG": str(systemctl_log),
            "FAKE_GIT_LOG": str(git_log),
            "PYTHON_BIN": "/definitely-missing-python",
        }
    )

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "update.sh")],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "拉取最新代码..." in result.stdout
    assert "通过 systemd 重启 switch-ip 服务: switch-ip" in result.stdout
    assert not (repo_root / ".venv").exists()

    systemctl_calls = systemctl_log.read_text(encoding="utf-8").splitlines()
    assert "show --property=LoadState --value switch-ip" in systemctl_calls
    assert "is-active --quiet switch-ip" in systemctl_calls
    assert "restart switch-ip" in systemctl_calls
    assert "stop switch-ip" not in systemctl_calls
    assert "start switch-ip" not in systemctl_calls

    git_calls = git_log.read_text(encoding="utf-8")
    assert "diff --quiet" in git_calls
    assert "diff --cached --quiet" in git_calls
    assert "pull --ff-only" in git_calls
