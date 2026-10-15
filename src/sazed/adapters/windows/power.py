"""Power actions. Each one is delayed a little so Sazed's reply is printed first.

Never called by tests: only `power_command` is tested.
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable

DELAY_SECONDS = 5
"""shutdown.exe's own countdown; `shutdown /a` cancels it."""
_SHORT_DELAY = 2.0

_COMMANDS: dict[str, list[str]] = {
    "shutdown": ["shutdown", "/s", "/t", str(DELAY_SECONDS)],
    "restart": ["shutdown", "/r", "/t", str(DELAY_SECONDS)],
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
        subprocess.run(power_command("shutdown"), check=True)

    def restart(self) -> None:
        subprocess.run(power_command("restart"), check=True)

    def sign_out(self) -> None:
        _later(lambda: subprocess.run(power_command("sign_out"), check=False))

    def sleep(self) -> None:
        import ctypes

        # SetSuspendState(hibernate=False, force=False, disable_wake_events=False)
        _later(lambda: ctypes.windll.powrprof.SetSuspendState(0, 0, 0))  # type: ignore[attr-defined]
