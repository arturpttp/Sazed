"""Monitor brightness through WMI. Only monitors that expose it respond; others are unsupported."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def _wmi() -> Any:
    import win32com.client

    return win32com.client.GetObject("winmgmts:\\\\.\\root\\WMI")


class WmiBrightness:
    def get(self) -> int | None:
        try:
            for monitor in _wmi().InstancesOf("WmiMonitorBrightness"):
                return int(monitor.CurrentBrightness)
        except Exception:
            log.warning("could not read brightness", exc_info=True)
        return None

    def set(self, percent: int) -> bool:
        try:
            monitors = list(_wmi().InstancesOf("WmiMonitorBrightnessMethods"))
            for monitor in monitors:
                # The dynamic call `monitor.WmiSetBrightness(0, n)` is rejected as an invalid
                # parameter (checked 2026-10-15); named in-parameters through ExecMethod_ work.
                params = monitor.Methods_("WmiSetBrightness").InParameters.SpawnInstance_()
                params.Properties_.Item("Timeout").Value = 0
                params.Properties_.Item("Brightness").Value = percent
                monitor.ExecMethod_("WmiSetBrightness", params)
            return bool(monitors)
        except Exception:
            log.warning("could not set brightness", exc_info=True)
            return False
