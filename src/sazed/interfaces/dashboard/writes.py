"""Write endpoints, without HTTP: validate the JSON body, run it on the editor's thread, answer
in pt-BR. Security (token, Origin, size, POST only) is checked by `server` before this runs.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sazed.runtime.editing import Editor, EditorUnavailable, NoteTarget, WriteOutcome

log = logging.getLogger(__name__)

NEXT_START = "Vale a partir do próximo início do Sazed."
GENERIC_ERROR = "Peço desculpas, Mestre Artur: não consegui gravar. Os detalhes estão no log."
MESSAGES: dict[str, str] = {
    "learned": "Guardado em minha mente de cobre.",
    "already_known": "Isso eu já sabia, Mestre Artur: nada foi guardado.",
    "conflict": ("Essa frase se parece muito com outro pedido que conheço. Guardar mesmo assim?"),
    "not_learnable": (
        "Esse pedido nunca é aprendido: sempre pedirei confirmação antes de executá-lo."
    ),
    "unknown": "Não encontrei esse item ou esse pedido.",
    "empty": "O texto ficou vazio depois de normalizado.",
    "saved": "Apelido guardado.",
    "app_unknown": "Não conheço esse programa no catálogo.",
    "exists": "Esse apelido já existe. Para mudar o destino, use Corrigir.",
    "forgotten": "Esquecido.",
    "not_found": "Não encontrei esse item; talvez já tenha sido removido.",
    "restored": "Desfeito: o item voltou, com suas notas.",
    "undo_expired": "Não há mais o que desfazer para esse item.",
    "undo_taken": "Não dá para desfazer: algo novo ocupou o lugar desse item.",
    "note_saved": "Nota guardada.",
    "note_removed": "Nota removida.",
    "unavailable": "O modelo não está disponível.",
}
NOTE_CODES = frozenset({"note_saved", "note_removed"})
"""Notes are for Mestre Artur; Sazed never reads them, so no 'next start' remark."""

FIELD_LABELS: dict[str, str] = {
    "ref": "item",
    "undo": "desfazer",
    "text": "texto",
    "intent": "pedido",
    "force": "forçar",
    "id": "item",
    "alias": "apelido",
    "target": "destino",
    "episode_id": "comando",
    "target_id": "item",
}
_ERRORS: dict[str, str] = {
    "missing": "é obrigatório",
    "string_too_short": "não pode ficar vazio",
    "string_too_long": "deve ter no máximo {max_length} caracteres",
    "string_type": "deve ser um texto",
    "string_pattern_mismatch": "não está no formato esperado",
    "int_type": "deve ser um número inteiro",
    "int_parsing": "deve ser um número inteiro",
    "int_from_float": "deve ser um número inteiro",
    "greater_than_equal": "deve ser no mínimo {ge}",
    "less_than_equal": "deve ser no máximo {le}",
    "bool_type": "deve ser verdadeiro ou falso",
    "bool_parsing": "deve ser verdadeiro ou falso",
    "literal_error": "deve ser um destes: {expected}",
    "extra_forbidden": "não é um campo aceito",
    "model_type": "o corpo deve ser um objeto JSON",
    "model_attributes_type": "o corpo deve ser um objeto JSON",
}
_FALLBACK = "valor inválido"


def describe_errors(err: ValidationError) -> str:
    parts = []
    for error in err.errors():
        field = ".".join(str(p) for p in error["loc"])
        label = FIELD_LABELS.get(field, field) or "corpo"
        context = {k: str(v).replace(" or ", " ou ") for k, v in error.get("ctx", {}).items()}
        template = _ERRORS.get(error["type"], _FALLBACK)
        parts.append(f"{label}: {template.format(**context)}")
    return "Dados inválidos: " + "; ".join(parts) + "."


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Text = Field(min_length=1, max_length=300)
Intent = Field(min_length=1, max_length=80)
ItemId = Field(ge=1, le=10**12)


class ForgetBody(_Body):
    ref: str = Field(min_length=2, max_length=20, pattern=r"^[ea][0-9]+$")


class UndoBody(_Body):
    undo: str = Field(min_length=1, max_length=64)


class ExampleAddBody(_Body):
    text: str = Text
    intent: str = Intent
    force: bool = False


class ExampleEditBody(_Body):
    id: int = ItemId
    text: str = Text
    intent: str = Intent
    force: bool = False


class AliasAddBody(_Body):
    alias: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=200)


class AliasEditBody(_Body):
    id: int = ItemId
    target: str = Field(min_length=1, max_length=200)


class LabelBody(_Body):
    episode_id: int = ItemId
    intent: str = Intent
    force: bool = False


class NoteAddBody(_Body):
    target: Literal["example", "alias", "episode"]
    target_id: int = ItemId
    text: str = Field(min_length=1, max_length=2000)


class NoteEditBody(_Body):
    id: int = ItemId
    text: str = Field(min_length=1, max_length=2000)


class NoteRemoveBody(_Body):
    id: int = ItemId


WRITE_ROUTES: dict[str, tuple[str, type[_Body]]] = {
    "/api/write/forget": ("forget", ForgetBody),
    "/api/write/undo": ("undo", UndoBody),
    "/api/write/example/add": ("example_add", ExampleAddBody),
    "/api/write/example/edit": ("example_edit", ExampleEditBody),
    "/api/write/alias/add": ("alias_add", AliasAddBody),
    "/api/write/alias/edit": ("alias_edit", AliasEditBody),
    "/api/write/episode/label": ("label", LabelBody),
    "/api/write/note/add": ("note_add", NoteAddBody),
    "/api/write/note/edit": ("note_edit", NoteEditBody),
    "/api/write/note/remove": ("note_remove", NoteRemoveBody),
}


def _answer(outcome: WriteOutcome) -> dict[str, Any]:
    message = MESSAGES[outcome.code]
    if outcome.ok and outcome.code not in NOTE_CODES:
        message = f"{message} {NEXT_START}"
    return {
        "ok": outcome.ok,
        "code": outcome.code,
        "message": message,
        "needs_force": outcome.code == "conflict",
        "ref": outcome.ref,
        "undo": outcome.undo,
    }


class WriteApi:
    """Every editor call runs on one worker thread (a SQLite connection is per thread)."""

    def __init__(self, editor: Editor) -> None:
        self._editor = editor
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sazed-editor")

    def status(self) -> dict[str, Any]:
        """Never loads anything: it only reports the editor's state."""
        return {"state": self._editor.state, "message": self._editor.message}

    def handle(self, path: str, raw: bytes) -> tuple[int, dict[str, Any]]:
        route = WRITE_ROUTES.get(path)
        if route is None:
            return 404, {"error": "Este endereço não existe no painel."}
        name, model = route
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return 400, {"error": "O corpo da requisição não é um JSON válido."}
        try:
            body = model.model_validate(data)  # all validation precedes the first write
        except ValidationError as err:
            return 400, {"error": describe_errors(err)}
        try:
            outcome: WriteOutcome = self._worker.submit(getattr(self, f"_{name}"), body).result()
        except EditorUnavailable as err:
            return 200, {**_answer(WriteOutcome(False, "unavailable")), "message": str(err)}
        except Exception:
            log.exception("dashboard write %s failed", path)
            return 500, {"error": GENERIC_ERROR}
        return 200, _answer(outcome)

    def close(self) -> None:
        self._worker.submit(self._editor.close).result()
        self._worker.shutdown()

    # one method per route, run on the worker thread ------------------------------

    def _forget(self, b: ForgetBody) -> WriteOutcome:
        return self._editor.forget(b.ref)

    def _undo(self, b: UndoBody) -> WriteOutcome:
        return self._editor.undo(b.undo)

    def _example_add(self, b: ExampleAddBody) -> WriteOutcome:
        return self._editor.learn(b.text, b.intent, force=b.force)

    def _example_edit(self, b: ExampleEditBody) -> WriteOutcome:
        return self._editor.edit_example(b.id, b.text, b.intent, force=b.force)

    def _alias_add(self, b: AliasAddBody) -> WriteOutcome:
        return self._editor.add_alias(b.alias, b.target)

    def _alias_edit(self, b: AliasEditBody) -> WriteOutcome:
        return self._editor.edit_alias(b.id, b.target)

    def _label(self, b: LabelBody) -> WriteOutcome:
        return self._editor.label(b.episode_id, b.intent, force=b.force)

    def _note_add(self, b: NoteAddBody) -> WriteOutcome:
        return self._editor.add_note(NoteTarget(b.target), b.target_id, b.text)

    def _note_edit(self, b: NoteEditBody) -> WriteOutcome:
        return self._editor.edit_note(b.id, b.text)

    def _note_remove(self, b: NoteRemoveBody) -> WriteOutcome:
        return self._editor.remove_note(b.id)
