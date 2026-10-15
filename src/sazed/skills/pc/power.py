"""Lock, shut down, restart, suspend, sign out. Every power action confirms and is never learned."""

from __future__ import annotations

from typing import Protocol

from sazed.core.outcomes import Locked, Outcome, Restarting, ShuttingDown, SigningOut, Suspending
from sazed.core.skill import IntentSpec, SkillContext, always
from sazed.core.types import Slots


class Power(Protocol):
    def lock(self) -> None: ...
    def shutdown(self) -> None: ...
    def restart(self) -> None: ...
    def sleep(self) -> None: ...
    def sign_out(self) -> None: ...


LOCK_EXAMPLES = (
    "bloqueia o computador",
    "bloqueia o pc",
    "trava o computador",
    "trava a tela",
    "bloqueia a tela",
    "tranca o computador",
    "bloquear o pc",
    "trava o pc",
    "bloqueia tudo",
    "tranca a tela",
)
SHUTDOWN_EXAMPLES = (
    "desliga o computador",
    "desliga o pc",
    "desligar o computador",
    "pode desligar o pc",
    "encerra o windows",
    "desliga a máquina",
    "apaga o computador",
    "desligar tudo",
    "desliga o computador agora",
    "quero desligar o pc",
)
RESTART_EXAMPLES = (
    "reinicia o computador",
    "reinicia o pc",
    "reiniciar o computador",
    "reinicializa o pc",
    "reinicia a máquina",
    "reboot no pc",
    "pode reiniciar o computador",
    "reiniciar o pc",
    "reinicia o windows",
    "quero reiniciar o computador",
)
SLEEP_EXAMPLES = (
    "suspende o computador",
    "suspende o pc",
    "coloca o pc pra dormir",
    "modo suspensão",
    "hiberna o computador",
    "põe o computador pra dormir",
    "suspender o pc",
    "deixa o pc em suspensão",
    "computador vai dormir",
    "coloca o computador em repouso",
)
SIGN_OUT_EXAMPLES = (
    "sai da minha conta",
    "faz logoff",
    "desloga do windows",
    "sair da conta",
    "faz logout",
    "encerra a sessão",
    "sair do usuário",
    "desconecta minha conta",
    "troca de usuário",
    "fecha a sessão",
)

POWER_INTENTS = frozenset({"pc_desligar", "pc_reiniciar", "pc_suspender", "pc_sair_conta"})


def _power(intent_id: str, examples: tuple[str, ...], describe: str) -> IntentSpec:
    # A learned phrase must never weaken a power confirmation (spec 2a §3.2).
    return IntentSpec(
        intent_id, examples, (), lambda s: describe, requires_confirmation=always, learnable=False
    )


class PowerSkill:
    id = "power"

    def __init__(self, power: Power) -> None:
        self._power = power
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec("pc_bloquear", LOCK_EXAMPLES, (), lambda s: "bloquear o computador"),
            _power("pc_desligar", SHUTDOWN_EXAMPLES, "desligar o computador"),
            _power("pc_reiniciar", RESTART_EXAMPLES, "reiniciar o computador"),
            _power("pc_suspender", SLEEP_EXAMPLES, "suspender o computador"),
            _power("pc_sair_conta", SIGN_OUT_EXAMPLES, "sair da sua conta"),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id == "pc_bloquear":
            self._power.lock()
            return Locked()
        if intent_id == "pc_desligar":
            self._power.shutdown()
            return ShuttingDown()
        if intent_id == "pc_reiniciar":
            self._power.restart()
            return Restarting()
        if intent_id == "pc_suspender":
            self._power.sleep()
            return Suspending()
        if intent_id == "pc_sair_conta":
            self._power.sign_out()
            return SigningOut()
        raise ValueError(f"unknown intent {intent_id}")
