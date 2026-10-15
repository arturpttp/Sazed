from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import BaseModel

from sazed.runtime.config import Config, ConfigError, load_config

ROOT = Path(__file__).resolve().parents[2]
ENGLISH_MARKERS = ("Input should", "Field required", "Value error", "Extra inputs", "should be")


def leaf_paths(model: type[BaseModel], prefix: tuple[str, ...] = ()) -> Iterator[tuple[str, ...]]:
    for name, field in model.model_fields.items():
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            yield from leaf_paths(annotation, (*prefix, name))
        else:
            yield (*prefix, name)


LEAVES = list(leaf_paths(Config))


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def toml_setting(path: tuple[str, ...], value: str) -> str:
    if len(path) == 1:
        return f"{path[0]} = {value}\n"
    return f"[{path[0]}]\n{path[1]} = {value}\n"


def test_leaf_walk_finds_nested_fields() -> None:
    assert ("nlu", "t_exec") in LEAVES and ("aliases",) in LEAVES


@pytest.mark.parametrize("path", LEAVES, ids=".".join)
def test_wrong_type_in_any_field_gets_a_pt_br_message(
    tmp_path: Path, path: tuple[str, ...]
) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, toml_setting(path, "[1, 2]")))
    message = str(caught.value)
    assert ".".join(path) in message
    assert not any(marker in message for marker in ENGLISH_MARKERS), message


def test_out_of_range_threshold(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[nlu]\nt_exec = 1.5\n"))
    assert "nlu.t_exec: deve ser no máximo 1" in str(caught.value)


def test_confirm_threshold_above_exec_threshold_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[nlu]\nt_exec = 0.8\nt_confirm = 0.9\n"))
    assert "t_confirm não pode ser maior que t_exec" in str(caught.value)


def test_unknown_key_is_rejected_in_pt_br(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[user]\nnome = 'Artur'\n"))
    assert "user.nome: não é uma chave reconhecida" in str(caught.value)


def test_malformed_toml_is_reported_in_pt_br(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as caught:
        load_config(write(tmp_path, "[user\nname = \n"))
    assert "TOML" in str(caught.value)
    assert not any(marker in str(caught.value) for marker in ENGLISH_MARKERS)


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path / "absent.toml") == Config()


def test_valid_file_is_read(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "[user]\nname = 'Kelsier'\n[aliases]\nzap = 'WhatsApp'\n"))
    assert config.user.name == "Kelsier"
    assert config.aliases == {"zap": "WhatsApp"}


def test_example_config_documents_the_real_defaults() -> None:
    assert load_config(ROOT / "config.example.toml") == Config()
