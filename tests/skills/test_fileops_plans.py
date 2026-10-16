import ntpath

import pytest

from sazed.core.outcomes import (
    BadName,
    IntoItself,
    NameTaken,
    NoRecycleBin,
    Protected,
    UndoStale,
)
from sazed.skills.pc.fileops import (
    Area,
    ChangePlan,
    ItemState,
    LoggedChange,
    describe_plan,
    human_size,
    plan_change,
    plan_undo,
)

P = r"C:\Users\a"
DL, DOCS, DESK = rf"{P}\Downloads", rf"{P}\Documents", rf"{P}\Desktop"
AREA = Area(
    roots=(P,), fixed=(P, DL, DOCS, DESK), trees=(rf"{P}\AppData",), realpath=ntpath.normpath
)
LABELS = {DL: "Downloads", DOCS: "Documentos", DESK: "Área de Trabalho"}
REPORT = ItemState(rf"{DL}\relatório.docx", False, 20_000, 1000.0, 0)
TRIP = ItemState(rf"{DL}\viagem", True, 2_469_606_195, 1000.0, 128)


def say(plan: object) -> str:
    assert isinstance(plan, ChangePlan), plan
    return describe_plan(plan, LABELS)


def test_move_a_file() -> None:
    plan = plan_change("mover", REPORT, DOCS, None, set(), AREA)
    assert isinstance(plan, ChangePlan)
    assert plan.target == rf"{DOCS}\relatório.docx" and plan.before == REPORT
    assert say(plan) == "Mover relatório.docx de Downloads para Documentos"


def test_a_clash_keeps_both_and_says_so() -> None:
    plan = plan_change("copiar", REPORT, DOCS, None, {"Relatório.docx"}, AREA)
    assert isinstance(plan, ChangePlan) and plan.renamed_for_clash
    assert plan.target == rf"{DOCS}\relatório (2).docx"
    assert say(plan) == (
        "Copiar relatório.docx de Downloads para Documentos. Já existe relatório.docx lá;"
        " vou salvar como relatório (2).docx"
    )


def test_a_folder_shows_what_is_inside() -> None:
    assert say(plan_change("apagar", TRIP, None, None, set(), AREA)) == (
        "Mandar a pasta viagem (128 arquivos, 2,3 GB) para a Lixeira"
    )
    assert say(plan_change("mover", TRIP, DESK, None, set(), AREA)) == (
        "Mover a pasta viagem (128 arquivos, 2,3 GB) de Downloads para Área de Trabalho"
    )


def test_rename_keeps_the_extension() -> None:
    plan = plan_change("renomear", REPORT, None, "Relatório Final", set(), AREA)
    assert isinstance(plan, ChangePlan) and plan.target == rf"{DL}\Relatório Final.docx"
    assert say(plan) == "Renomear relatório.docx para Relatório Final.docx"


def test_create_a_folder() -> None:
    plan = plan_change("criar", None, DESK, "Viagem 2025", set(), AREA)
    assert isinstance(plan, ChangePlan) and plan.is_dir and plan.source is None
    assert say(plan) == "Criar a pasta Viagem 2025 em Área de Trabalho"


@pytest.mark.parametrize("folder", [TRIP.path, rf"{TRIP.path}\fotos"])
def test_a_folder_never_goes_into_itself(folder: str) -> None:
    assert plan_change("mover", TRIP, folder, None, set(), AREA) == IntoItself("viagem")
    assert plan_change("copiar", TRIP, folder, None, set(), AREA) == IntoItself("viagem")


def test_moving_into_the_folder_it_is_already_in_is_refused() -> None:
    assert plan_change("mover", REPORT, DL, None, {"relatório.docx"}, AREA) == NameTaken(
        "relatório.docx"
    )


def test_rename_onto_a_taken_name_is_refused_never_numbered() -> None:
    taken = {"relatório.docx", "final.docx"}
    assert plan_change("renomear", REPORT, None, "final", taken, AREA) == NameTaken("final.docx")


def test_create_onto_a_taken_name_is_refused() -> None:
    assert plan_change("criar", None, DESK, "viagem", {"Viagem"}, AREA) == NameTaken("viagem")


@pytest.mark.parametrize("kind", ["renomear", "criar"])
def test_a_bad_new_name_is_explained(kind: str) -> None:
    source = REPORT if kind == "renomear" else None
    found = plan_change(kind, source, DESK, "a/b", set(), AREA)  # type: ignore[arg-type]
    assert isinstance(found, BadName) and found.name == "a/b"


def test_protected_items_and_destinations() -> None:
    downloads = ItemState(DL, True, 0, 0.0, 3)
    assert plan_change("apagar", downloads, None, None, set(), AREA) == Protected("Downloads")
    assert plan_change("renomear", downloads, None, "x", set(), AREA) == Protected("Downloads")
    windows = r"C:\Windows"
    assert plan_change("mover", REPORT, windows, None, set(), AREA) == Protected("Windows")


def test_no_recycle_bin_means_no_delete() -> None:
    found = plan_change("apagar", REPORT, None, None, set(), AREA, can_recycle=False)
    assert found == NoRecycleBin("relatório.docx")


def test_human_sizes_in_pt_br() -> None:
    assert human_size(512) == "512 bytes"
    assert human_size(20_000) == "20 KB"
    assert human_size(2_469_606_195) == "2,3 GB"
    assert human_size(150 * 2**20) == "150 MB"


# undo -------------------------------------------------------------------------------------

MOVED = LoggedChange(
    1, "mover", REPORT.path, rf"{DOCS}\relatório.docx", False, 20_000, 2000.0, None
)
NOW_MOVED = ItemState(MOVED.target, False, 20_000, 2000.0, 0)


def test_undo_a_move_puts_it_back() -> None:
    plan = plan_undo(MOVED, NOW_MOVED, set())
    assert isinstance(plan, ChangePlan)
    assert (plan.kind, plan.source, plan.target, plan.undo_of) == (
        "mover",
        MOVED.target,
        MOVED.source,
        1,
    )
    assert say(plan) == "Devolver relatório.docx de Documentos para Downloads"


@pytest.mark.parametrize(
    "now",
    [
        None,
        ItemState(MOVED.target, False, 99, 2000.0, 0),
        ItemState(MOVED.target, False, 20_000, 9.0, 0),
    ],
)
def test_undo_refuses_when_the_item_changed_or_is_gone(now: ItemState | None) -> None:
    assert plan_undo(MOVED, now, set()) == UndoStale("relatório.docx")


def test_undo_refuses_when_the_original_name_is_taken_again() -> None:
    assert plan_undo(MOVED, NOW_MOVED, {"RELATÓRIO.docx"}) == UndoStale("relatório.docx")


def test_undo_a_rename() -> None:
    renamed = LoggedChange(
        2, "renomear", REPORT.path, rf"{DL}\final.docx", False, 20_000, 3.0, None
    )
    plan = plan_undo(renamed, ItemState(renamed.target, False, 20_000, 3.0, 0), set())
    assert say(plan) == "Voltar o nome de final.docx para relatório.docx"


def test_undo_a_copy_or_a_new_folder_sends_it_to_the_recycle_bin() -> None:
    copied = LoggedChange(
        3, "copiar", REPORT.path, rf"{DOCS}\relatório.docx", False, 20_000, 4.0, None
    )
    plan = plan_undo(copied, ItemState(copied.target, False, 20_000, 4.0, 0), set())
    assert isinstance(plan, ChangePlan) and plan.kind == "apagar"
    assert say(plan) == "Mandar a cópia relatório.docx (em Documentos) para a Lixeira"
    made = LoggedChange(4, "criar", None, rf"{DESK}\viagem", True, 0, 5.0, None)
    plan = plan_undo(made, ItemState(made.target, True, 0, 5.0, 0), set())
    assert say(plan) == "Mandar a pasta viagem (em Área de Trabalho) para a Lixeira"


def test_undo_a_delete_restores_from_the_recycle_bin() -> None:
    deleted = LoggedChange(5, "apagar", None, REPORT.path, False, 20_000, 1000.0, "ref")
    plan = plan_undo(deleted, None, set())
    assert isinstance(plan, ChangePlan)
    assert (plan.kind, plan.target, plan.recycle_ref) == ("restaurar", REPORT.path, "ref")
    assert say(plan) == "Tirar relatório.docx da Lixeira de volta para Downloads"
    back_already = ItemState(REPORT.path, False, 20_000, 1000.0, 0)
    assert plan_undo(deleted, back_already, set()) == UndoStale("relatório.docx")
