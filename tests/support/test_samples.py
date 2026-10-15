from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

import pytest

from support.samples import sample_instance, sample_value


class Color(Enum):
    RED = "red"
    BLUE = "blue"


@dataclass(frozen=True)
class Everything:
    text: str
    count: int
    ratio: float
    flag: bool
    maybe: str | None
    many: tuple[str, ...]
    mapping: Mapping[str, int]
    color: Color


@dataclass(frozen=True)
class Unsupported:
    items: set[int]


def test_sample_instance_fills_every_field_with_a_value_of_the_right_type() -> None:
    item = sample_instance(Everything)
    assert item == Everything(
        text="Exemplo",
        count=7,
        ratio=0.5,
        flag=True,
        maybe="Exemplo",
        many=("Exemplo", "Exemplo"),
        mapping={},
        color=Color.RED,
    )


def test_sample_value_refuses_unknown_types_instead_of_guessing() -> None:
    with pytest.raises(TypeError):
        sample_instance(Unsupported)


def test_sample_value_of_plain_str() -> None:
    assert sample_value(str) == "Exemplo"
