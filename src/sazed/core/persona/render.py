"""Render outcomes, decisions and prompts in Sazed's voice. Pure: the RNG is passed in."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from random import Random

from sazed.core.decisions import AskSlot, Confirm, ConfirmReason, Decision
from sazed.core.outcomes import AppNotFound, Outcome
from sazed.core.persona.definition import EXTRA_FIELDS, TEMPLATES, Prompt

Renderable = Outcome | Decision | Prompt


def template_key(item: Renderable) -> str:
    if isinstance(item, Prompt):
        return item.value
    if isinstance(item, AppNotFound) and item.suggestion is not None:
        return "AppNotFound.suggestion"
    if isinstance(item, Confirm) and item.reason is ConfirmReason.DESTRUCTIVE:
        return "ConfirmDestructive"
    if isinstance(item, AskSlot) and item.candidates:
        return "AskSlotChoice"
    return type(item).__name__


def format_fields(item: object) -> dict[str, str]:
    """Template values from a dataclass: strings and ints as-is, tuples as a numbered list.

    Mappings (slots) and enums are internal and never formatted.
    """
    if isinstance(item, Prompt) or not hasattr(item, "__dataclass_fields__"):
        return {}
    values: dict[str, str] = {}
    for f in fields(item):  # type: ignore[arg-type]
        value = getattr(item, f.name)
        if isinstance(value, tuple):
            values[f.name] = ", ".join(f"{i}) {v}" for i, v in enumerate(value, start=1))
        elif isinstance(value, str | int) and not isinstance(value, bool):
            values[f.name] = str(value)
    return values


def render(
    item: Renderable, *, nome: str, rng: Random, extra: Mapping[str, str] | None = None
) -> str:
    key = template_key(item)
    values = {**format_fields(item), **(extra or {}), "mestre": f"Mestre {nome}"}
    missing = set(EXTRA_FIELDS.get(key, ())) - values.keys()
    if missing:
        raise KeyError(f"rendering {key} needs {sorted(missing)}")
    return rng.choice(TEMPLATES[key]).format(**values)
