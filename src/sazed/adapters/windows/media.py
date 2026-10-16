"""System media session (Spotify, browsers, …) through WinRT. Async calls run to completion here."""

from __future__ import annotations

import asyncio
from typing import Any

from sazed.skills.pc.media import NowPlayingInfo


async def _session() -> Any:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    return (await Manager.request_async()).get_current_session()


async def _toggle() -> bool:
    session = await _session()
    return session is not None and bool(await session.try_toggle_play_pause_async())


async def _next() -> bool:
    session = await _session()
    return session is not None and bool(await session.try_skip_next_async())


async def _previous() -> bool:
    session = await _session()
    return session is not None and bool(await session.try_skip_previous_async())


async def _now_playing() -> NowPlayingInfo | None:
    session = await _session()
    if session is None:
        return None
    props = await session.try_get_media_properties_async()
    title = str(props.title or "").strip()
    return NowPlayingInfo(title, str(props.artist or "").strip()) if title else None


class WinRtMedia:
    def toggle(self) -> bool:
        return asyncio.run(_toggle())

    def next(self) -> bool:
        return asyncio.run(_next())

    def previous(self) -> bool:
        return asyncio.run(_previous())

    def now_playing(self) -> NowPlayingInfo | None:
        return asyncio.run(_now_playing())
