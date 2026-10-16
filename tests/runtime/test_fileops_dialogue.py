"""File changes in conversation: one question with the exact effect, "sim" applies, undo."""

from datetime import datetime

from sazed.core.outcomes import (
    ChangeUndone,
    FileChangeProposed,
    FileMoved,
    PlanChanged,
)
from sazed.skills.pc.fileops import ItemState
from sazed.skills.pc.files import FileHit
from support.harness import Make

DL, DOCS = r"C:\U\Downloads", r"C:\U\Documents"
REPORT = ItemState(rf"{DL}\relatório.docx", False, 20_000, 1000.0, 0)
REPORT_HIT = FileHit(REPORT.path, "relatório.docx", "Downloads", datetime(2026, 10, 14, 9))
MOVE = "move o relatório pra pasta documentos"
SCRIPT = {MOVE: {"arquivo_mover": 0.85, "arquivo_copiar": 0.84}}


def file_changes(h) -> list[tuple[object, ...]]:  # type: ignore[no-untyped-def]
    # Re-read from SQLite, never trusted from the reply.
    return h.store._conn.execute(
        "SELECT kind, source, target, undone_at IS NOT NULL FROM file_changes ORDER BY id"
    ).fetchall()


def test_a_move_is_asked_once_with_its_exact_effect(make: Make) -> None:
    h = make(SCRIPT, files=[REPORT_HIT], disk=[REPORT])
    r = h.say(MOVE)
    assert isinstance(r.outcome, FileChangeProposed)
    assert r.text == "Mover relatório.docx de Downloads para Documentos. Confirma, Mestre Artur?"
    assert h.changer.calls == []


def test_yes_applies_the_plan_and_logs_it(make: Make) -> None:
    h = make(SCRIPT, files=[REPORT_HIT], disk=[REPORT])
    h.say(MOVE)
    r = h.say("sim")
    assert r.outcome == FileMoved("relatório.docx", "Documentos")
    assert h.changer.state(rf"{DOCS}\relatório.docx") is not None
    assert file_changes(h) == [("mover", REPORT.path, rf"{DOCS}\relatório.docx", 0)]


def test_no_changes_nothing(make: Make) -> None:
    h = make(SCRIPT, files=[REPORT_HIT], disk=[REPORT])
    h.say(MOVE)
    h.say("não")
    assert h.changer.calls == [] and file_changes(h) == []


def test_another_phrase_drops_the_plan(make: Make) -> None:
    h = make(
        {**SCRIPT, "aumenta o volume": {"volume_aumentar": 0.97}}, files=[REPORT_HIT], disk=[REPORT]
    )
    h.say(MOVE)
    h.say("aumenta o volume")
    h.say("sim")
    assert h.changer.calls == []


def test_a_file_changed_before_yes_is_left_alone(make: Make) -> None:
    h = make(SCRIPT, files=[REPORT_HIT], disk=[REPORT])
    h.say(MOVE)
    h.changer.items[REPORT.path.lower()] = ItemState(REPORT.path, False, 1, 9.0, 0)
    assert h.say("sim").outcome == PlanChanged()
    assert h.changer.calls == [] and file_changes(h) == []


def test_undo_is_confirmed_then_applied_and_closes_the_log_row(make: Make) -> None:
    h = make(SCRIPT, files=[REPORT_HIT], disk=[REPORT])
    h.say(MOVE)
    h.say("sim")
    r = h.say("desfaz isso")
    assert r.text == (
        "Devolver relatório.docx de Documentos para Downloads. Confirma, Mestre Artur?"
    )
    assert h.changer.state(REPORT.path) is None  # not yet
    r = h.say("sim")
    assert isinstance(r.outcome, ChangeUndone)
    assert h.changer.state(REPORT.path) is not None
    assert file_changes(h) == [("mover", REPORT.path, rf"{DOCS}\relatório.docx", 1)]


def test_undo_with_nothing_done(make: Make) -> None:
    h = make({})
    assert h.say("desfaz").text == "Não há nada para desfazer, Mestre Artur."


def test_choosing_among_files_resumes_the_plan(make: Make) -> None:
    a = ItemState(rf"{DL}\nota 1.txt", False, 1, 1.0, 0)
    b = ItemState(rf"{DL}\nota 2.txt", False, 1, 1.0, 0)
    hits = [
        FileHit(i.path, i.path.rsplit("\\", 1)[1], "Downloads", datetime(2026, 10, 14, 8 + n))
        for n, i in enumerate((a, b))
    ]
    h = make({"apaga a nota": {"arquivo_apagar": 0.97}}, files=hits, disk=[a, b])
    r = h.say("apaga a nota")
    assert "1) nota 2.txt" in r.text
    r = h.say("o segundo")
    assert r.text == "Mandar nota 1.txt para a Lixeira. Confirma, Mestre Artur?"
    h.say("sim")
    assert h.changer.state(a.path) is None and h.changer.state(b.path) is not None


def test_nothing_from_a_file_change_is_ever_learned(make: Make) -> None:
    h = make(
        {**SCRIPT, "bota o relatório nos documentos": {"arquivo_mover": 0.85}},
        files=[REPORT_HIT],
        disk=[REPORT],
    )
    h.say("leva aquele negócio pra lá")  # not understood: a later success would offer to learn it
    h.say(MOVE)
    h.say("sim")
    h.say("desfaz isso")
    h.say("sim")
    assert h.store.learned() == []
