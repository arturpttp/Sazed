"""Power actions. Each one is delayed a little so Sazed's reply is printed first.

Never called by tests: only `power_command` is tested. shutdown.exe's own countdown is never
used: any `/t` above 0 implies `/f`, which kills apps without their "save changes?" prompt.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable

_SHORT_DELAY = 2.0

_COMMANDS: dict[str, list[str]] = {
    "shutdown": ["shutdown", "/s", "/t", "0"],
    "restart": ["shutdown", "/r", "/t", "0"],
    "sign_out": ["shutdown", "/l"],  # /l takes no countdown
}


def power_command(kind: str) -> list[str]:
    if kind not in _COMMANDS:
        raise ValueError(f"unknown power action {kind!r}")
    return list(_COMMANDS[kind])


def _later(action: Callable[[], object]) -> None:
    threading.Timer(_SHORT_DELAY, action).start()


class WindowsPower:
    def lock(self) -> None:
        import ctypes

        if not ctypes.windll.user32.LockWorkStation():  # type: ignore[attr-defined]
            raise OSError("LockWorkStation failed")

    def shutdown(self) -> None:
        _later(lambda: subprocess.run(power_command("shutdown"), check=False))

    def restart(self) -> None:
        _later(lambda: subprocess.run(power_command("restart"), check=False))

    def sign_out(self) -> None:
        _later(lambda: subprocess.run(power_command("sign_out"), check=False))

    def sleep(self) -> None:
        import ctypes

        # SetSuspendState(hibernate=False, force=False, disable_wake_events=False)
        _later(lambda: ctypes.windll.powrprof.SetSuspendState(0, 0, 0))  # type: ignore[attr-defined]
