import ntpath
from datetime import datetime

from fakes.ports import FakeChangeLog, FakeChanger, FakeFolders, FakeSearch
from sazed.core.outcomes import (
    AmbiguousSlot,
    ChangeUndone,
    FileBusy,
    FileChangeProposed,
    FileCopied,
    FileMoved,
    FileNotFound,
    FileRecycled,
    FileRenamed,
    FolderCreated,
    FolderNotFound,
    NoRecycleBin,
    NothingToUndo,
    NotInRecycleBin,
    PlanChanged,
    Protected,
    UndoStale,
)
from sazed.core.skill import SkillContext
from sazed.core.types import Slots, SlotValue, Unmatched
from sazed.skills.pc.fileops import Area, FileOpsSkill, ItemState
from sazed.skills.pc.files import FileHit

CTX = SkillContext(now=datetime(2026, 10, 16, 15, 0))
P = r"C:\Users\a"
DL, DOCS, DESK = rf"{P}\Downloads", rf"{P}\Documents", rf"{P}\Desktop"
FOLDERS = {"Downloads": DL, "Documentos": DOCS, "Área de Trabalho": DESK}
AREA = Area(
    roots=(P,), fixed=(P, DL, DOCS, DESK), trees=(rf"{P}\AppData",), realpath=ntpath.normpath
)
REPORT = ItemState(rf"{DL}\relatório.docx", False, 20_000, 1000.0, 0)
TRIP = ItemState(rf"{DL}\viagem", True, 10, 1000.0, 1)
TRIP_PHOTO = ItemState(rf"{DL}\viagem\f.jpg", False, 10, 1000.0, 0)
DIRS = [ItemState(f, True, 0, 1.0, 0) for f in (DL, DOCS, DESK)]


def hit(state: ItemState) -> FileHit:
    folder, name = state.path.rsplit("\\", 1)
    return FileHit(state.path, name, folder.rsplit("\\", 1)[1], datetime(2026, 10, 16, 9))


def make(items: list[ItemState], *, hits: list[FileHit] | None = None, **kw: object):  # type: ignore[no-untyped-def]
    disk = FakeChanger([*DIRS, *items], **kw)  # type: ignore[arg-type]
    log = FakeChangeLog()
    folder_hits = [hit(i) for i in items if i.is_dir]
    search = FakeSearch(hits if hits is not None else [hit(i) for i in items if not i.is_dir])
    search.folder_hits = folder_hits
    skill = FileOpsSkill(FakeFolders(dict(FOLDERS)), search, disk, log, AREA)
    return skill, disk, log


def slots(**values: str | Unmatched) -> Slots:
    return {
        k: v if isinstance(v, Unmatched) else SlotValue(k, v, str(v), 1.0)
        for k, v in values.items()
    }


def propose_and_apply(skill: FileOpsSkill, intent: str, given: Slots) -> object:
    proposed = skill.execute(intent, given, CTX)
    assert isinstance(proposed, FileChangeProposed), proposed
    return skill.apply_pending(CTX)


def test_move_is_proposed_with_its_exact_effect_and_nothing_happens_yet() -> None:
    skill, disk, log = make([REPORT])
    found = skill.execute(
        "arquivo_mover", slots(item="arquivo:relatório", destino="Documentos"), CTX
    )
    assert found == FileChangeProposed("Mover relatório.docx de Downloads para Documentos")
    assert disk.calls == [] and log.rows == []


def test_applying_the_plan_moves_and_logs() -> None:
    skill, disk, log = make([REPORT])
    done = propose_and_apply(
        skill, "arquivo_mover", slots(item="arquivo:relatório", destino="Documentos")
    )
    assert done == FileMoved("relatório.docx", "Documentos")
    assert disk.state(rf"{DOCS}\relatório.docx") is not None
    change = log.latest_open()
    assert change is not None and (change.kind, change.source, change.target) == (
        "mover",
        REPORT.path,
        rf"{DOCS}\relatório.docx",
    )


def test_a_file_changed_after_the_question_is_left_alone() -> None:
    skill, disk, log = make([REPORT])
    skill.execute("arquivo_mover", slots(item="arquivo:relatório", destino="Documentos"), CTX)
    disk.items[REPORT.path.lower()] = ItemState(REPORT.path, False, 99, 2000.0, 0)
    assert skill.apply_pending(CTX) == PlanChanged()
    assert disk.calls == [] and log.rows == []


def test_a_file_removed_after_the_question_is_left_alone() -> None:
    skill, disk, _ = make([REPORT])
    skill.execute("arquivo_apagar", slots(item="arquivo:relatório"), CTX)
    del disk.items[REPORT.path.lower()]
    assert skill.apply_pending(CTX) == PlanChanged()
    assert disk.calls == []


def test_a_target_taken_after_the_question_is_left_alone() -> None:
    skill, disk, _ = make([REPORT])
    skill.execute("arquivo_mover", slots(item="arquivo:relatório", destino="Documentos"), CTX)
    disk.items[rf"{DOCS}\relatório.docx".lower()] = ItemState(
        rf"{DOCS}\relatório.docx", False, 1, 1.0, 0
    )
    assert skill.apply_pending(CTX) == PlanChanged()
    assert disk.calls == []


def test_copy_keeps_both_on_a_clash() -> None:
    other = ItemState(rf"{DOCS}\relatório.docx", False, 5, 1.0, 0)
    skill, disk, _ = make([REPORT, other], hits=[hit(REPORT)])
    proposed = skill.execute(
        "arquivo_copiar", slots(item="arquivo:relatório", destino="Documentos"), CTX
    )
    assert isinstance(proposed, FileChangeProposed)
    assert "vou salvar como relatório (2).docx" in proposed.action
    assert skill.apply_pending(CTX) == FileCopied("relatório (2).docx", "Documentos")
    assert disk.state(rf"{DOCS}\relatório (2).docx") is not None
    assert disk.state(REPORT.path) is not None


def test_rename_and_create_and_delete() -> None:
    skill, disk, _ = make([REPORT, TRIP, TRIP_PHOTO])
    assert propose_and_apply(
        skill, "arquivo_renomear", slots(item="arquivo:relatório", novo_nome="Final")
    ) == FileRenamed("relatório.docx", "Final.docx")
    assert propose_and_apply(
        skill, "pasta_criar", slots(novo_nome="Notas", destino="Documentos")
    ) == FolderCreated("Notas", "Documentos")
    assert disk.state(rf"{DOCS}\Notas") is not None
    assert propose_and_apply(skill, "arquivo_apagar", slots(item="pasta:viagem")) == (
        FileRecycled("viagem")
    )
    assert disk.state(TRIP_PHOTO.path) is None


def test_create_defaults_to_the_desktop() -> None:
    skill, disk, _ = make([])
    assert propose_and_apply(skill, "pasta_criar", slots(novo_nome="Viagem")) == FolderCreated(
        "Viagem", "Área de Trabalho"
    )


def test_the_latest_download() -> None:
    skill, _, _ = make([REPORT])
    found = skill.execute(
        "arquivo_mover", slots(item="ultimo:Downloads", destino="Documentos"), CTX
    )
    assert found == FileChangeProposed("Mover relatório.docx de Downloads para Documentos")


def test_a_destination_found_by_name_and_one_that_does_not_exist() -> None:
    projects = ItemState(rf"{DOCS}\Projetos", True, 0, 1.0, 0)
    skill, _, _ = make([REPORT, projects])
    found = skill.execute(
        "arquivo_mover",
        slots(item="arquivo:relatório", destino=Unmatched("destino", "projetos", None)),
        CTX,
    )
    assert found == FileChangeProposed("Mover relatório.docx de Downloads para Projetos")
    missing = slots(item="arquivo:relatório", destino=Unmatched("destino", "xyz", None))
    assert skill.execute("arquivo_mover", missing, CTX) == FolderNotFound("xyz")


def test_several_files_are_listed_and_a_pick_resumes() -> None:
    a = ItemState(rf"{DL}\nota 1.txt", False, 1, 1.0, 0)
    b = ItemState(rf"{DL}\nota 2.txt", False, 1, 1.0, 0)
    skill, _, _ = make([a, b])
    amb = skill.execute("arquivo_apagar", slots(item="arquivo:nota"), CTX)
    assert isinstance(amb, AmbiguousSlot) and amb.slot == "item"
    picked = skill.execute("arquivo_apagar", slots(item=amb.candidates[1]), CTX)
    assert isinstance(picked, FileChangeProposed) and "nota" in picked.action


def test_not_found_protected_busy_and_no_recycle_bin() -> None:
    skill, _, _ = make([])
    assert skill.execute("arquivo_apagar", slots(item="arquivo:x"), CTX) == FileNotFound(
        "x", "nenhum arquivo chamado"
    )
    skill, _, _ = make([], hits=[])
    downloads = slots(item="pasta:downloads")
    skill._search.folder_hits = [hit(DIRS[0])]  # type: ignore[attr-defined]
    assert skill.execute("arquivo_apagar", downloads, CTX) == Protected("Downloads")
    skill, disk, _ = make([REPORT], busy=[REPORT.path])
    skill.execute("arquivo_mover", slots(item="arquivo:relatório", destino="Documentos"), CTX)
    assert skill.apply_pending(CTX) == FileBusy("mover", "relatório.docx")
    skill, _, _ = make([REPORT], no_bin=True)
    assert skill.execute("arquivo_apagar", slots(item="arquivo:relatório"), CTX) == NoRecycleBin(
        "relatório.docx"
    )


def test_nothing_pending_means_nothing_to_apply() -> None:
    skill, disk, _ = make([REPORT])
    assert skill.apply_pending(CTX) == PlanChanged()
    assert disk.calls == []


# undo -------------------------------------------------------------------------------------


def test_undo_with_nothing_logged() -> None:
    skill, _, _ = make([])
    assert skill.propose_undo(CTX) == NothingToUndo()


def test_undo_a_move_is_proposed_then_applied() -> None:
    skill, disk, log = make([REPORT])
    propose_and_apply(skill, "arquivo_mover", slots(item="arquivo:relatório", destino="Documentos"))
    assert skill.propose_undo(CTX) == FileChangeProposed(
        "Devolver relatório.docx de Documentos para Downloads"
    )
    assert skill.apply_pending(CTX) == ChangeUndone(
        "Devolver relatório.docx de Documentos para Downloads"
    )
    assert disk.state(REPORT.path) is not None
    assert log.latest_open() is None


def test_undo_a_delete_restores_from_the_recycle_bin() -> None:
    skill, disk, _ = make([TRIP, TRIP_PHOTO])
    propose_and_apply(skill, "arquivo_apagar", slots(item="pasta:viagem"))
    assert isinstance(skill.propose_undo(CTX), FileChangeProposed)
    assert isinstance(skill.apply_pending(CTX), ChangeUndone)
    assert disk.state(TRIP_PHOTO.path) is not None


def test_undo_after_the_bin_was_emptied_closes_the_change() -> None:
    skill, disk, log = make([REPORT])
    propose_and_apply(skill, "arquivo_apagar", slots(item="arquivo:relatório"))
    disk.bin.clear()
    skill.propose_undo(CTX)
    assert skill.apply_pending(CTX) == NotInRecycleBin("relatório.docx")
    assert log.latest_open() is None


def test_undo_refuses_after_the_file_changed() -> None:
    skill, disk, _ = make([REPORT])
    propose_and_apply(skill, "arquivo_mover", slots(item="arquivo:relatório", destino="Documentos"))
    moved = rf"{DOCS}\relatório.docx"
    disk.items[moved.lower()] = ItemState(moved, False, 1, 9999.0, 0)
    assert skill.propose_undo(CTX) == UndoStale("relatório.docx")


def test_every_file_change_intent_confirms_itself_and_is_never_learned() -> None:
    skill, _, _ = make([])
    assert {s.id for s in skill.intents} == {
        "arquivo_mover",
        "arquivo_copiar",
        "arquivo_renomear",
        "arquivo_apagar",
        "pasta_criar",
    }
    assert all(s.confirms_itself and not s.learnable and not s.repeatable for s in skill.intents)


# found on the real machine (2026-10-16) ----------------------------------------------------


def test_a_known_folder_named_as_the_item_is_refused_by_its_pt_br_name() -> None:
    other_downloads = ItemState(rf"{DOCS}\modpack\downloads", True, 1, 1.0, 1)
    skill, disk, _ = make([other_downloads])
    assert skill.execute("arquivo_apagar", slots(item="pasta:downloads"), CTX) == Protected(
        "Downloads"
    )
    assert skill.execute(
        "arquivo_renomear", slots(item="pasta:documentos", novo_nome="docs"), CTX
    ) == Protected("Documentos")
    assert disk.calls == []


def test_search_results_outside_the_area_are_never_offered() -> None:
    inside = ItemState(rf"{DOCS}\windows", True, 0, 1.0, 0)
    appdata = ItemState(rf"{P}\AppData\Local\Packages\windows", True, 0, 1.0, 0)
    skill, _, _ = make([REPORT, inside, appdata])
    found = skill.execute(
        "arquivo_mover",
        slots(item="arquivo:relatório", destino=Unmatched("destino", "windows", None)),
        CTX,
    )
    assert found == FileChangeProposed("Mover relatório.docx de Downloads para windows")


def test_only_protected_matches_means_protected() -> None:
    appdata = ItemState(rf"{P}\AppData\Local\viagem", True, 0, 1.0, 0)
    skill, _, _ = make([appdata])
    assert skill.execute("arquivo_apagar", slots(item="pasta:viagem"), CTX) == Protected("viagem")
