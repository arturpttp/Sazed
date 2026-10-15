"""Master volume through the AudioControl port."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import Muted, Outcome, Unmuted, VolumeChanged, VolumeSet
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue
from sazed.skills.pc.levels import clamp, int_slot, invalid_level, level_label, stepped


class AudioControl(Protocol):
    def get_volume(self) -> int: ...
    def set_volume(self, percent: int) -> None: ...
    def set_muted(self, muted: bool) -> None: ...


SET_EXAMPLES = (
    "volume em 30",
    "coloca o volume em 50",
    "deixa o som em 20 por cento",
    "ajusta o volume pra 70",
    "volume no máximo",
    "volume na metade",
    "põe o volume em 10",
    "define o volume para 40",
    "som em 80",
    "quero o volume em 25",
    "volume no mínimo",
    "coloca o som no máximo",
    "muda o volume para 60",
)
UP_EXAMPLES = (
    "aumenta o volume",
    "aumenta o som",
    "sobe o volume",
    "sobe o som",
    "mais alto",
    "aumenta o volume em 20",
    "sobe o volume em 10",
    "aumenta mais o volume",
    "coloca mais alto",
    "volume mais alto",
    "aumenta o áudio",
    "sobe o áudio um pouco",
    "tá baixo aumenta o som",
    "aumenta o volume em 30",
)
DOWN_EXAMPLES = (
    "diminui o volume",
    "abaixa o som",
    "baixa o volume",
    "mais baixo",
    "diminui o volume em 20",
    "abaixa o volume em 10",
    "abaixa um pouco",
    "reduz o volume",
    "volume mais baixo",
    "diminui o som",
    "abaixa o áudio",
    "tá alto abaixa o som",
    "baixa o som um pouco",
    "diminui o volume em 30",
)
MUTE_EXAMPLES = (
    "muta",
    "silencia",
    "mudo",
    "tira o som",
    "coloca no mudo",
    "tira do mudo",
    "desmuta",
    "volta o som",
    "ativa o som",
    "silencia o computador",
    "deixa mudo",
)


def _percent_label(slots: Slots) -> str:
    n = int_slot(slots, "percent")
    return f"{n}%" if n is not None else "um valor"


def _mute_label(slots: Slots) -> str:
    mute = slots.get("mudo")
    if isinstance(mute, SlotValue) and mute.value is False:
        return "reativar o som"
    return "silenciar o som"


# "abaixa o volume para 100" names the level to end at, in either direction.
_LEVEL = SlotSpec("alvo", False, "Em quanto devo deixar o volume?")


class VolumeSkill:
    id = "volume"

    def __init__(self, audio: AudioControl) -> None:
        self._audio = audio
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "volume_definir",
                SET_EXAMPLES,
                (SlotSpec("percent", True, "Em quanto devo deixar o volume?"),),
                describe=lambda s: f"deixar o volume em {_percent_label(s)}",
            ),
            IntentSpec(
                "volume_aumentar",
                UP_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo aumentar?"), _LEVEL),
                describe=level_label("aumentar o volume", "o volume"),
                repeatable=True,
            ),
            IntentSpec(
                "volume_diminuir",
                DOWN_EXAMPLES,
                (SlotSpec("percent", False, "Quanto devo diminuir?"), _LEVEL),
                describe=level_label("diminuir o volume", "o volume"),
                repeatable=True,
            ),
            IntentSpec(
                "volume_mudo",
                MUTE_EXAMPLES,
                (SlotSpec("mudo", False, "Devo silenciar ou reativar o som?"),),
                describe=_mute_label,
            ),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id in ("volume_definir", "volume_aumentar", "volume_diminuir"):
            invalid = invalid_level(slots)
            if invalid is not None:
                return invalid
        if intent_id == "volume_definir":
            percent = int_slot(slots, "percent")
            if percent is None:
                raise ValueError("volume_definir called without its required slot 'percent'")
            self._audio.set_volume(clamp(percent))
            return VolumeSet(clamp(percent))
        if intent_id in ("volume_aumentar", "volume_diminuir"):
            sign = 1 if intent_id == "volume_aumentar" else -1
            level, absolute = stepped(self._audio.get_volume(), sign, slots)
            self._audio.set_volume(level)
            return VolumeSet(level) if absolute else VolumeChanged(level)
        if intent_id == "volume_mudo":
            mute = slots.get("mudo")
            muted = bool(mute.value) if isinstance(mute, SlotValue) else True
            self._audio.set_muted(muted)
            return Muted() if muted else Unmuted()
        raise ValueError(f"unknown intent {intent_id}")
