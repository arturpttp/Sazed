"""Build a sample instance of any dataclass from its type hints, for schema-driven tests."""

import types
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints


def sample_value(tp: Any) -> Any:
    if tp is str:
        return "Exemplo"
    if tp is bool:
        return True
    if tp is int:
        return 7
    if tp is float:
        return 0.5
    origin = get_origin(tp)
    if origin in (Union, types.UnionType):
        first = next(a for a in get_args(tp) if a is not type(None))
        return sample_value(first)
    if origin is tuple:
        item = sample_value(get_args(tp)[0])
        return (item, item)
    if origin is Mapping or tp is Mapping:
        return {}
    if isinstance(tp, type) and issubclass(tp, Enum):
        return next(iter(tp))
    if isinstance(tp, type) and is_dataclass(tp):
        return sample_instance(tp)
    raise TypeError(f"no sample value for {tp!r}")


def sample_instance(cls: type) -> Any:
    hints = get_type_hints(cls)
    return cls(**{f.name: sample_value(hints[f.name]) for f in fields(cls)})
