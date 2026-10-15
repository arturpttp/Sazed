"""Master volume through pycaw. The default device is re-read on every call."""

from __future__ import annotations

from typing import Any


def _endpoint() -> Any:
    from pycaw.pycaw import AudioUtilities

    speakers = AudioUtilities.GetSpeakers()
    endpoint = getattr(speakers, "EndpointVolume", None)
    if endpoint is not None:
        return endpoint
    # Older pycaw: activate the interface by hand.
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume

    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


class PycawAudio:
    def get_volume(self) -> int:
        return round(_endpoint().GetMasterVolumeLevelScalar() * 100)

    def set_volume(self, percent: int) -> None:
        _endpoint().SetMasterVolumeLevelScalar(max(0, min(100, percent)) / 100, None)

    def set_muted(self, muted: bool) -> None:
        _endpoint().SetMute(int(muted), None)

    def is_muted(self) -> bool:
        return bool(_endpoint().GetMute())
