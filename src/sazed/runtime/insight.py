"""What the dashboard needs from the rest of Sazed: skills, ports, config, paths, and a
pt-BR explanation of each recorded decision. Reads only; never executes a skill.
"""

from __future__ import annotations

import inspect
import tomllib
import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn, Protocol

from sazed.adapters.sqlite.reader import CoppermindReader, CoppermindUnavailable
from sazed.core.decisions import Confirm, ConfirmReason, Execute
from sazed.core.outcomes import FAILURE_NAMES
from sazed.core.policy import IntentRequirements, Thresholds, decide
from sazed.core.skill import IntentSpec, Skill, never
from sazed.core.types import IntentScore, ParseResult, Utterance
from sazed.nlu.normalize import normalize, strip_accents
from sazed.runtime.config import Config, load_config
from sazed.skills.pc.apps import AppEntry, AppsSkill
from sazed.skills.pc.volume import VolumeSkill

__all__ = [
    "FAILURE_OUTCOMES",
    "CoppermindReader",
    "CoppermindUnavailable",
    "Thresholds",
]

FAILURE_OUTCOMES: frozenset[str] = FAILURE_NAMES

PORT_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "AppCatalog": (
        "Lê os atalhos (.lnk) do Menu Iniciar do usuário e de todos os usuários.",
        "StartMenuCatalog",
    ),
    "AppLauncher": (
        "Abre programas e fecha suas janelas (WM_CLOSE; nunca encerra à força).",
        "WindowsLauncher",
    ),
    "AudioControl": ("Lê e altera o volume principal e o mudo.", "PycawAudio"),
}
NO_DESCRIPTION = ("Sem descrição.", "?")


class _Inert:
    """Stands in for every port: listing a skill must never reach the OS."""

    def __getattr__(self, name: str) -> NoReturn:
        raise RuntimeError(f"the dashboard never calls ports (tried {name})")


def skills_for_listing() -> list[Skill]:
    """The wired skills, built with inert ports (tests assert they match `build_app`)."""
    inert: Any = _Inert()
    return [AppsSkill(inert, inert), VolumeSkill(inert)]


@dataclass(frozen=True)
class SlotInfo:
    name: str
    required: bool
    question: str


@dataclass(frozen=True)
class IntentInfo:
    id: str
    description: str
    examples: int
    example_texts: tuple[str, ...]
    slots: tuple[SlotInfo, ...]
    confirmation: str


@dataclass(frozen=True)
class SkillInfo:
    id: str
    intents: tuple[IntentInfo, ...]


def _describe(spec: IntentSpec) -> str:
    try:
        return spec.describe({})
    except Exception:
        return spec.id


def capabilities(skills: Sequence[Skill]) -> list[SkillInfo]:
    return [
        SkillInfo(
            skill.id,
            tuple(
                IntentInfo(
                    spec.id,
                    _describe(spec),
                    len(spec.examples),
                    tuple(spec.examples),
                    tuple(SlotInfo(s.name, s.required, s.question) for s in spec.slots),
                    "nunca" if spec.requires_confirmation is never else "conforme o pedido",
                )
                for spec in skill.intents
            ),
        )
        for skill in skills
    ]


@dataclass(frozen=True)
class PortInfo:
    name: str
    skill: str
    methods: tuple[str, ...]
    description: str
    adapter: str


def ports(skills: Sequence[Skill]) -> list[PortInfo]:
    """Derived from each skill's constructor annotations, so a new port shows up by itself."""
    found: list[PortInfo] = []
    for skill in skills:
        hints = typing.get_type_hints(type(skill).__init__)
        for name, hint in hints.items():
            if name == "return" or not getattr(hint, "_is_protocol", False):
                continue
            methods = tuple(
                m for m, _ in inspect.getmembers(hint, inspect.isfunction) if not m.startswith("_")
            )
            description, adapter = PORT_DESCRIPTIONS.get(hint.__name__, NO_DESCRIPTION)
            found.append(PortInfo(hint.__name__, skill.id, methods, description, adapter))
    return found


# explanations ----------------------------------------------------------------


def _score_verdict(ranking: Sequence[tuple[str, float]], th: Thresholds) -> tuple[str, str]:
    """Reuses `core.policy.decide` on the scores alone, so the rule is never restated."""
    scores = tuple(IntentScore(i, s) for i, s in ranking)
    parse = ParseResult(Utterance("", "", datetime.min), scores, {}, frozenset())
    verdict = decide(parse, IntentRequirements(frozenset(), False), th)
    if not scores:
        return "NotUnderstood", "Nenhum pedido conhecido foi comparado."
    top = scores[0]
    if isinstance(verdict, Execute):
        gap = top.score - (scores[1].score if len(scores) > 1 else 0.0)
        return "Execute", (
            f"A melhor pontuação ({top.intent_id} {top.score:.3f}) atingiu o limiar de execução"
            f" ({th.t_exec}) e a folga para o segundo ({gap:.3f}) é de pelo menos {th.g_min}."
        )
    if isinstance(verdict, Confirm) and verdict.reason is ConfirmReason.SMALL_GAP:
        second = scores[1]
        return "Confirm", (
            f"Dois pedidos ficaram próximos ({top.intent_id} {top.score:.3f} e"
            f" {second.intent_id} {second.score:.3f}; folga menor que {th.g_min}):"
            " pedi confirmação."
        )
    if isinstance(verdict, Confirm):
        return "Confirm", (
            f"A pontuação {top.score:.3f} ({top.intent_id}) ficou entre o limiar de confirmação"
            f" ({th.t_confirm}) e o de execução ({th.t_exec}): pedi confirmação."
        )
    return "NotUnderstood", (
        f"A melhor pontuação ({top.intent_id} {top.score:.3f}) ficou abaixo do limiar de"
        f" confirmação ({th.t_confirm})."
    )


def _spec(skills: Sequence[Skill], intent_id: str | None) -> IntentSpec | None:
    return next((s for k in skills for s in k.intents if s.id == intent_id), None)


def explain(
    ranking: Sequence[tuple[str, float]],
    decision: str,
    slots: Mapping[str, str],
    intent_id: str | None,
    skills: Sequence[Skill],
    th: Thresholds,
) -> str:
    """Why this decision, reconstructed from the stored scores and the *current* thresholds."""
    if decision == "control":
        return "Resposta de diálogo (sim, não, esquece, de novo…), não um pedido novo."
    if decision == "error":
        return "Erro interno ao tratar o pedido; os detalhes estão no arquivo de log."
    verdict, reason = _score_verdict(ranking, th)
    if decision == "AskSlot":
        spec = _spec(skills, intent_id)
        ambiguous = {n: v.split("|") for n, v in slots.items() if "|" in v}
        if ambiguous:
            name, options = next(iter(ambiguous.items()))
            return f"O detalhe '{name}' ficou ambíguo entre {', '.join(options)}: perguntei qual."
        missing = sorted((spec.required if spec else frozenset()) - set(slots))
        questions = [spec.question(m) for m in missing] if spec else []
        detail = " ".join(questions) or "um detalhe obrigatório"
        return f"Entendi o pedido, mas faltou um detalhe obrigatório: {detail}"
    if decision == "Confirm" and verdict == "Execute":
        return (
            "A pontuação bastava para executar, mas este pedido exige confirmação"
            " (ação destrutiva ou com mais de uma possibilidade)."
        )
    if decision not in {"Execute", "Confirm", "NotUnderstood"}:
        return f"Decisão '{decision}'. {reason}"
    if verdict != decision:
        return f"{reason} (Com os limiares atuais a decisão seria outra: eles mudaram desde então.)"
    return reason


def learned_for(
    utterance: str,
    examples: Sequence[tuple[str, str]],
    aliases: Sequence[tuple[str, str]],
) -> list[str]:
    """What the coppermind holds that came from (or applies to) this utterance."""
    text = normalize(utterance)
    words = set(strip_accents(text).split())
    found = [f"exemplo '{t}' → {intent}" for t, intent in examples if t == text]
    found += [f"apelido '{a}' → {v}" for a, v in aliases if strip_accents(a) in words]
    return found


# config and paths --------------------------------------------------------------


@dataclass(frozen=True)
class ConfigView:
    config: Config
    effective: dict[str, Any]
    raw: dict[str, Any]


def config_view(path: Path) -> ConfigView:
    """Raises ConfigError (pt-BR) for an invalid file, exactly like Sazed's own startup."""
    config = load_config(path)
    raw = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return ConfigView(config, config.model_dump(mode="json"), raw)


@dataclass(frozen=True)
class PathRow:
    label: str
    path: str
    exists: bool
    size: int | None


def _row(label: str, path: Path) -> PathRow:
    size = path.stat().st_size if path.is_file() else None
    return PathRow(label, str(path), path.exists(), size)


def path_rows(config: Config, config_path: Path) -> list[PathRow]:
    data = config.data.dir
    model = config.model.embedder_path
    return [
        _row("config.toml", config_path),
        _row("Pasta de dados", data),
        _row("Mente de cobre", data / "coppermind.db"),
        _row("Logs de Sazed", data / "logs" / "sazed.log"),
        _row("Logs do painel", data / "logs" / "painel.log"),
        _row("Pasta do modelo", model),
        _row("Modelo (model.onnx)", model / "model.onnx"),
        _row("Tokenizador (tokenizer.json)", model / "tokenizer.json"),
        _row("Variante do modelo (VARIANT)", model / "VARIANT"),
    ]


def coppermind_path(config: Config) -> Path:
    return config.data.dir / "coppermind.db"


class _Catalog(Protocol):
    def entries(self) -> Sequence[AppEntry]: ...


def default_catalog() -> Callable[[], Sequence[AppEntry]]:
    """The real Start-menu catalog, scanned on first use."""
    from sazed.adapters.windows.catalog import StartMenuCatalog

    catalog: _Catalog = StartMenuCatalog()
    return catalog.entries
