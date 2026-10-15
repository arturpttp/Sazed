from __future__ import annotations

from dataclasses import dataclass

from sazed.core.decisions import Decision
from sazed.core.outcomes import Outcome


@dataclass(frozen=True)
class Response:
    """What the user sees. `text` is always rendered by the persona."""

    text: str
    outcome: Outcome | None
    decision: Decision | None
