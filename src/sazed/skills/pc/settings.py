"""Open Windows Settings, optionally at a named page."""

from __future__ import annotations

from dataclasses import dataclass

from sazed.core.outcomes import Outcome, SettingsOpened, UnknownSettingsPage
from sazed.core.skill import IntentSpec, SkillContext, SlotSpec
from sazed.core.types import Slots, SlotValue, Unmatched
from sazed.skills.pc.web import UriOpener


@dataclass(frozen=True)
class SettingsPage:
    label: str
    names: tuple[str, ...]
    uri: str


SETTINGS_PAGES: tuple[SettingsPage, ...] = (
    SettingsPage("bluetooth", ("bluetooth", "dispositivos"), "ms-settings:bluetooth"),
    SettingsPage("rede", ("wi-fi", "wifi", "rede", "internet"), "ms-settings:network-wifi"),
    SettingsPage("som", ("som", "áudio"), "ms-settings:sound"),
    SettingsPage("tela", ("tela", "vídeo", "monitor", "resolução"), "ms-settings:display"),
    SettingsPage("atualizações", ("atualizações", "windows update"), "ms-settings:windowsupdate"),
    SettingsPage("aplicativos", ("aplicativos", "programas"), "ms-settings:appsfeatures"),
    SettingsPage("armazenamento", ("armazenamento", "disco"), "ms-settings:storagesense"),
    SettingsPage("energia", ("energia", "bateria", "suspensão"), "ms-settings:powersleep"),
    SettingsPage("notificações", ("notificações",), "ms-settings:notifications"),
    SettingsPage(
        "plano de fundo",
        ("plano de fundo", "papel de parede", "personalização"),
        "ms-settings:personalization-background",
    ),
    SettingsPage("privacidade", ("privacidade",), "ms-settings:privacy"),
    SettingsPage("mouse", ("mouse",), "ms-settings:mousetouchpad"),
    SettingsPage("teclado", ("teclado", "digitação"), "ms-settings:typing"),
    SettingsPage("impressoras", ("impressoras", "impressora"), "ms-settings:printers"),
    SettingsPage("data e hora", ("data e hora", "relógio"), "ms-settings:dateandtime"),
    SettingsPage("contas", ("contas", "minha conta"), "ms-settings:yourinfo"),
    SettingsPage("sobre", ("sobre", "sistema", "informações do sistema"), "ms-settings:about"),
)
PAGE_NAMES: tuple[str, ...] = tuple(n for p in SETTINGS_PAGES for n in p.names)
_BY_NAME = {n: p for p in SETTINGS_PAGES for n in p.names}
HOME_URI = "ms-settings:"

SETTINGS_EXAMPLES = (
    "abre as configurações",
    "abre as configurações de bluetooth",
    "abre as configurações de som",
    "configurações de rede",
    "abre o painel de configurações",
    "abre as configurações do windows",
    "mostra as configurações de tela",
    "quero mudar o plano de fundo",
    "abre as configurações de wifi",
    "abre as configurações de atualização",
)


def _describe(slots: Slots) -> str:
    page = slots.get("pagina")
    if isinstance(page, SlotValue):
        return f"abrir as configurações de {_BY_NAME[str(page.value)].label}"
    return "abrir as configurações"


class SettingsSkill:
    id = "settings"

    def __init__(self, opener: UriOpener) -> None:
        self._opener = opener
        self.intents: tuple[IntentSpec, ...] = (
            IntentSpec(
                "abrir_configuracao",
                SETTINGS_EXAMPLES,
                (SlotSpec("pagina", False, "Qual página das configurações devo abrir?"),),
                describe=_describe,
            ),
        )

    def execute(self, intent_id: str, slots: Slots, ctx: SkillContext) -> Outcome:
        if intent_id != "abrir_configuracao":
            raise ValueError(f"unknown intent {intent_id}")
        page = slots.get("pagina")
        if isinstance(page, Unmatched):
            return UnknownSettingsPage(page.raw)
        if isinstance(page, SlotValue):
            found = _BY_NAME[str(page.value)]
            self._opener.open(found.uri)
            return SettingsOpened(found.label)
        self._opener.open(HOME_URI)
        return SettingsOpened("início")
