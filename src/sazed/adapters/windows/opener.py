"""Open web addresses, Settings pages and app ids with the Windows shell."""

from __future__ import annotations

import os

_ALLOWED_PREFIXES = (
    "http://",
    "https://",
    "ms-settings:",
    "ms-screenclip:",
    "shell:appsfolder\\",
)


def is_allowed_uri(uri: str) -> bool:
    """Only the kinds of address Sazed builds itself: never a local file or program path."""
    return uri.lower().startswith(_ALLOWED_PREFIXES)


class ShellOpener:
    def open(self, uri: str) -> None:
        if not is_allowed_uri(uri):
            raise ValueError("refusing to open an address of an unexpected kind")
        os.startfile(uri)  # type: ignore[attr-defined]  # Windows only
