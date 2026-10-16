"""The write layer without HTTP: validation, pt-BR messages, dispatch to the editor."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sazed.interfaces.dashboard.writes import (
    FIELD_LABELS,
    MESSAGES,
    NEXT_START,
    WRITE_ROUTES,
    WriteApi,
    describe_errors,
)
from sazed.runtime.admin import AliasResult, LabelResult
from sazed.runtime.config import Config, DataConfig
from sazed.runtime.editing import Editor, EditorUnavailable
from support.editing import NAMES, AppFactory

T = datetime(2026, 10, 15, 12, 0)


def make(tmp_path: Path, factory: AppFactory | None = None) -> tuple[WriteApi, AppFactory]:
    factory = factory or AppFactory()
    editor = Editor(
        Config(data=DataConfig(dir=tmp_path)),
        make_app=factory,
        app_names=lambda: NAMES,
        clock=lambda: T,
    )
    return WriteApi(editor), factory


def post(api: WriteApi, path: str, body: Any) -> tuple[int, dict[str, Any]]:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return api.handle(path, raw)


def test_every_result_code_has_a_pt_br_message() -> None:
    codes = {r.value for r in LabelResult} | {r.value for r in AliasResult}
    codes |= {
        "forgotten",
        "not_found",
        "restored",
        "undo_expired",
        "undo_taken",
        "note_saved",
        "note_removed",
        "empty",
        "unavailable",
    }
    assert codes <= set(MESSAGES)


def test_every_body_field_has_a_pt_br_label() -> None:
    fields = {name for model in WRITE_ROUTES.values() for name in model[1].model_fields}
    assert fields <= set(FIELD_LABELS)


def bad_values(model: type[BaseModel]) -> list[tuple[str, Any]]:
    cases: list[tuple[str, Any]] = []
    for name, info in model.model_fields.items():
        annotation = str(info.annotation)
        if "int" in annotation:
            cases += [(name, "abc"), (name, 0)]
        elif "bool" in annotation:
            cases.append((name, "talvez"))
        else:
            cases += [(name, ""), (name, 7), (name, "x" * 5000)]
    return cases


@pytest.mark.parametrize("path", sorted(WRITE_ROUTES))
def test_every_invalid_field_is_explained_in_pt_br(tmp_path: Path, path: str) -> None:
    api, factory = make(tmp_path)
    model = WRITE_ROUTES[path][1]
    for field, value in bad_values(model):
        status, payload = post(api, path, {field: value})
        assert status == 400, (path, field, value)
        error = payload["error"]
        assert error.startswith("Dados inválidos:")
        assert "valor inválido" not in error, (path, field, value, error)
        for english in ("Input should", "Field required", "String should", "Extra inputs"):
            assert english not in error
    assert factory.calls == 0


def test_unknown_fields_and_non_objects_are_refused(tmp_path: Path) -> None:
    api, _ = make(tmp_path)
    status, payload = post(api, "/api/write/forget", {"ref": "e1", "sql": "DROP"})
    assert status == 400 and "não é um campo aceito" in payload["error"]
    status, payload = post(api, "/api/write/forget", [1, 2])
    assert status == 400 and "objeto JSON" in payload["error"]
    status, payload = post(api, "/api/write/forget", b"{nao e json")
    assert (status, payload["error"]) == (400, "O corpo da requisição não é um JSON válido.")


def test_unknown_write_path(tmp_path: Path) -> None:
    api, _ = make(tmp_path)
    assert post(api, "/api/write/nada", {})[0] == 404


def test_a_successful_write_says_when_it_takes_effect(tmp_path: Path) -> None:
    api, _ = make(tmp_path)
    status, payload = post(api, "/api/write/alias/add", {"alias": "zap", "target": "WhatsApp"})
    assert status == 200
    assert payload["ok"] is True and payload["code"] == "saved"
    assert NEXT_START in payload["message"]


def test_conflict_offers_force(tmp_path: Path) -> None:
    api, _ = make(tmp_path)
    body = {"text": "fecha o chrome", "intent": "abrir_app"}
    status, payload = post(api, "/api/write/example/add", body)
    assert (status, payload["ok"], payload["code"], payload["needs_force"]) == (
        200,
        False,
        "conflict",
        True,
    )
    status, payload = post(api, "/api/write/example/add", {**body, "force": True})
    assert payload["ok"] is True


def test_power_intent_is_refused_with_an_explanation(tmp_path: Path) -> None:
    api, _ = make(tmp_path)
    _, payload = post(api, "/api/write/example/add", {"text": "apaga", "intent": "pc_desligar"})
    assert payload["ok"] is False and payload["code"] == "not_learnable"
    assert "confirmação" in payload["message"]


def test_forget_returns_an_undo(tmp_path: Path) -> None:
    api, _ = make(tmp_path)
    post(api, "/api/write/alias/add", {"alias": "zap", "target": "WhatsApp"})
    _, payload = post(api, "/api/write/forget", {"ref": "a1"})
    assert payload["ok"] is True and payload["undo"]
    _, payload = post(api, "/api/write/undo", {"undo": payload["undo"]})
    assert (payload["ok"], payload["code"]) == (True, "restored")


def test_missing_model_is_a_pt_br_refusal_not_a_crash(tmp_path: Path) -> None:
    api, _ = make(tmp_path, AppFactory(EditorUnavailable("Não encontrei o modelo em X.")))
    status, payload = post(api, "/api/write/example/add", {"text": "oi", "intent": "abrir_app"})
    assert (status, payload["ok"], payload["code"]) == (200, False, "unavailable")
    assert payload["message"] == "Não encontrei o modelo em X."


def test_an_unexpected_error_is_logged_not_shown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    api, _ = make(tmp_path, AppFactory(RuntimeError("SELECT * FROM segredo")))
    status, payload = post(api, "/api/write/example/add", {"text": "oi", "intent": "abrir_app"})
    assert status == 500
    assert "SELECT" not in json.dumps(payload)
    assert "SELECT * FROM segredo" in caplog.text


def test_editor_status_never_loads(tmp_path: Path) -> None:
    api, factory = make(tmp_path)
    assert api.status() == {"state": "idle", "message": None}
    assert factory.calls == 0


def test_describe_errors_falls_back_politely() -> None:
    class Odd(BaseModel):
        when: datetime

    try:
        Odd.model_validate({"when": "ontem"})
    except Exception as err:  # noqa: BLE001 - only the message matters here
        assert describe_errors(err) == "Dados inválidos: when: valor inválido."  # type: ignore[arg-type]
