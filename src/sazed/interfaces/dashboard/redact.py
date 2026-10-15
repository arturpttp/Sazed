"""Hide sensitive configuration values before they reach the page. Pure.

The rule is general, not a list of today's keys: any key whose name contains one of
SENSITIVE_PARTS is replaced whole, including a whole section.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

SENSITIVE_PARTS = ("secret", "token", "password", "key")
REDACTED = "••• (oculto)"


@dataclass(frozen=True)
class ConfigRow:
    key: str
    value: object
    origin: str
    """"arquivo" (set in config.toml) or "padrão" (built-in default)."""


def is_sensitive(name: str) -> bool:
    lowered = name.lower()
    return any(part in lowered for part in SENSITIVE_PARTS)


def redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(k): REDACTED if is_sensitive(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def _has(raw: Mapping[str, object], path: tuple[str, ...]) -> bool:
    node: object = raw
    for part in path:
        if not isinstance(node, Mapping) or part not in node:
            return False
        node = node[part]
    return True


def config_rows(effective: Mapping[str, object], raw: Mapping[str, object]) -> list[ConfigRow]:
    rows: list[ConfigRow] = []

    def walk(node: Mapping[str, object], path: tuple[str, ...]) -> None:
        for key, value in node.items():
            here = (*path, str(key))
            origin = "arquivo" if _has(raw, here) else "padrão"
            if is_sensitive(str(key)):
                rows.append(ConfigRow(".".join(here), REDACTED, origin))
            elif isinstance(value, Mapping) and value:
                walk(value, here)
            else:
                rows.append(ConfigRow(".".join(here), redact(value), origin))

    walk(effective, ())
    return rows
