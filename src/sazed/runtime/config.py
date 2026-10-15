"""config.toml, validated at startup. Every message a person can see is pt-BR."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "multilingual-e5-small"


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Sazed" if base else Path.home() / ".sazed"


DEFAULT_CONFIG_PATH = default_data_dir() / "config.toml"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserConfig(_Section):
    name: str = Field("Artur", min_length=1)


class NluConfig(_Section):
    # Tuned against tests/fixtures/nlu_cases.toml with scripts/tune_thresholds.py (int8 model).
    t_exec: float = Field(0.94, ge=0, le=1)
    t_confirm: float = Field(0.88, ge=0, le=1)
    g_min: float = Field(0.01, ge=0, le=1)

    @model_validator(mode="after")
    def _confirm_below_exec(self) -> NluConfig:
        if self.t_confirm > self.t_exec:
            raise ValueError("t_confirm não pode ser maior que t_exec")
        return self


class LearningConfig(_Section):
    t_conflict: float = Field(0.92, ge=0, le=1)
    t_dup: float = Field(0.97, ge=0, le=1)


class DialogueConfig(_Section):
    context_ttl_seconds: float = Field(60.0, gt=0)


class ModelConfig(_Section):
    embedder_path: Path = DEFAULT_MODEL_DIR


class DataConfig(_Section):
    dir: Path = Field(default_factory=default_data_dir)


class LoggingConfig(_Section):
    debug: bool = False


class Config(_Section):
    user: UserConfig = Field(default_factory=UserConfig)
    nlu: NluConfig = Field(default_factory=NluConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    dialogue: DialogueConfig = Field(default_factory=DialogueConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    aliases: dict[str, str] = Field(default_factory=dict)


class ConfigError(Exception):
    """Startup must stop. `str(error)` is a pt-BR message meant for the user."""


_MESSAGES = {
    "float_parsing": "deve ser um número",
    "float_type": "deve ser um número",
    "greater_than_equal": "deve ser no mínimo {ge}",
    "less_than_equal": "deve ser no máximo {le}",
    "greater_than": "deve ser maior que {gt}",
    "string_too_short": "não pode ficar vazio",
    "string_type": "deve ser um texto",
    "bool_parsing": "deve ser verdadeiro ou falso (true/false)",
    "bool_type": "deve ser verdadeiro ou falso (true/false)",
    "extra_forbidden": "não é uma chave reconhecida",
    "path_type": "deve ser um caminho",
    "dict_type": "deve ser uma tabela",
    "model_type": "deve ser uma seção [tabela]",
    "model_attributes_type": "deve ser uma seção [tabela]",
}
_FALLBACK = "valor inválido"


def _message(error: Any) -> str:
    context = error.get("ctx", {})
    if error["type"] == "value_error":
        return str(context.get("error", _FALLBACK))
    return _MESSAGES.get(error["type"], _FALLBACK).format(**context)


def _describe(err: ValidationError) -> list[str]:
    lines = []
    for error in err.errors():
        where = ".".join(str(part) for part in error["loc"]) or "arquivo"
        lines.append(f"- {where}: {_message(error)}")
    return lines


def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        raise ConfigError(
            f"Não consegui ler {path}: o arquivo não está em formato TOML válido."
        ) from None
    try:
        return Config.model_validate(data)
    except ValidationError as err:
        raise ConfigError(
            "\n".join([f"Configuração inválida em {path}:", *_describe(err)])
        ) from None
