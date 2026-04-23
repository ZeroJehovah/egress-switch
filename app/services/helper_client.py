from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


def _default_runner(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


@dataclass(slots=True)
class HelperResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


class HelperClient:
    def __init__(self, helper_path: Path, timeout: int, runner=_default_runner) -> None:
        self.helper_path = helper_path
        self.timeout = timeout
        self.runner = runner

    def switch_ip(self, target_ip: str) -> HelperResult:
        if not self.helper_path.exists():
            raise FileNotFoundError(f"切换脚本不存在: {self.helper_path}")

        result = self.runner([str(self.helper_path), target_ip], timeout=self.timeout)
        return HelperResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
