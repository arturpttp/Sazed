from datetime import datetime

from fakes.ports import FakeFileOpener, FakeFolders, FakeSearch
from sazed.core.outcomes import (
    AmbiguousSlot,
    FileGone,
    FileNotFound,
    FileOpened,
    FolderNotFound,
    FolderOpened,
    NothingRecent,
    ProgramRevealed,
    RecentFiles,
    SearchUnavailable,
)
from sazed.core.skill import SkillContext
from sazed.core.types import Slots, SlotValue, Unmatched
from sazed.skills.pc.files import FileHit, FilesSkill

NOW = datetime(2026, 10, 16, 15, 0)
CTX = SkillContext(now=NOW)
DL = "C:/U/Downloads"
SHOTS = "C:/U/Pictures/Screenshots"
FOLDERS = {"Downloads": DL, "Capturas de Tela": SHOTS, "Projetos": None}


def hit(path: str, modified: datetime = NOW) -> FileHit:
    folder, name = path.rsplit("/", 1)
    return FileHit(path, name, folder.rsplit("/", 1)[-1], modified)


def file_slot(name: str, kind: str | None = None) -> Slots:
    slots: dict[str, SlotValue | Unmatched] = {"arquivo": SlotValue("arquivo", name, name, 1.0)}
    if kind is not None:
        slots["tipo"] = SlotValue("tipo", kind, kind, 1.0)
    return slots


def folder_slot(name: str) -> Slots:
    return {"pasta": SlotValue("pasta", name, name.lower(), 1.0)}


def make(hits: list[FileHit], *, fail: bool = False, existing: set[str] | None = None):  # type: ignore[no-untyped-def]
    opener = FakeFileOpener({h.path for h in hits} if existing is None else existing)
    search = FakeSearch(hits, fail=fail)
    return FilesSkill(FakeFolders(FOLDERS), search, opener), search, opener


def test_open_a_known_folder() -> None:
    skill, _, opener = make([])
    assert skill.execute("abrir_pasta", folder_slot("Downloads"), CTX) == FolderOpened("Downloads")
    assert opener.opened == [DL]


def test_a_configured_folder_that_is_missing_and_an_unknown_one() -> None:
    skill, _, opener = make([])
    assert skill.execute("abrir_pasta", folder_slot("Projetos"), CTX) == FolderNotFound("Projetos")
    unknown: Slots = {"pasta": Unmatched("pasta", "xyzzy", None)}
    assert skill.execute("abrir_pasta", unknown, CTX) == FolderNotFound("xyzzy")
    assert opener.opened == []


def test_one_match_opens() -> None:
    skill, _, opener = make([hit(f"{DL}/contrato.pdf")])
    assert skill.execute("abrir_arquivo", file_slot("contrato"), CTX) == FileOpened("contrato.pdf")
    assert opener.opened == [f"{DL}/contrato.pdf"]


def test_the_kind_narrows_the_search() -> None:
    skill, search, _ = make([hit(f"{DL}/gastos.xlsx"), hit(f"{DL}/gastos.pdf")])
    found = skill.execute("abrir_arquivo", file_slot("gastos", "planilha"), CTX)
    assert found == FileOpened("gastos.xlsx")
    assert search.calls[0][1] == (".xlsx", ".xls", ".ods", ".csv")


def test_one_exact_name_opens_even_with_partial_matches() -> None:
    skill, _, opener = make([hit(f"{DL}/relatorio final.docx"), hit(f"{DL}/Relatório.docx")])
    assert skill.execute("abrir_arquivo", file_slot("relatório"), CTX) == FileOpened(
        "Relatório.docx"
    )
    assert opener.opened == [f"{DL}/Relatório.docx"]


def test_several_matches_list_the_five_newest_and_a_pick_opens_it() -> None:
    hits = [hit(f"{DL}/nota {i}.txt", datetime(2026, 10, 16, 8 + i, 0)) for i in range(7)]
    skill, _, opener = make(hits)
    amb = skill.execute("abrir_arquivo", file_slot("nota"), CTX)
    assert isinstance(amb, AmbiguousSlot) and amb.slot == "arquivo"
    assert amb.candidates == tuple(
        f"nota {i}.txt (Downloads, hoje {8 + i:02d}:00)" for i in (6, 5, 4, 3, 2)
    )
    assert skill.execute("abrir_arquivo", file_slot(amb.candidates[1]), CTX) == FileOpened(
        "nota 5.txt"
    )
    assert opener.opened == [f"{DL}/nota 5.txt"]


def test_a_program_chosen_from_a_list_is_revealed_not_run() -> None:
    hits = [hit(f"{DL}/setup.lnk"), hit(f"{DL}/setup.pdf", datetime(2026, 10, 15))]
    skill, _, opener = make(hits)
    amb = skill.execute("abrir_arquivo", file_slot("setup"), CTX)
    assert isinstance(amb, AmbiguousSlot)
    chosen = file_slot(amb.candidates[0])
    assert skill.execute("abrir_arquivo", chosen, CTX) == ProgramRevealed("setup.lnk")
    assert opener.opened == []
    assert opener.revealed == [f"{DL}/setup.lnk"]


def test_a_single_program_hit_is_revealed_too() -> None:
    skill, _, opener = make([hit(f"{DL}/instalar.bat")])
    assert skill.execute("abrir_arquivo", file_slot("instalar"), CTX) == ProgramRevealed(
        "instalar.bat"
    )
    assert opener.opened == []


def test_nothing_found_names_the_kind() -> None:
    skill, _, _ = make([])
    assert skill.execute("abrir_arquivo", file_slot("gastos", "planilha"), CTX) == FileNotFound(
        "gastos", "nenhuma planilha chamada"
    )
    assert skill.execute("abrir_arquivo", file_slot("gastos"), CTX) == FileNotFound(
        "gastos", "nenhum arquivo chamado"
    )


def test_search_failure_is_explained() -> None:
    skill, _, _ = make([], fail=True)
    assert skill.execute("abrir_arquivo", file_slot("x"), CTX) == SearchUnavailable()
    assert skill.execute("listar_recentes", {}, CTX) == SearchUnavailable()


def test_a_file_deleted_after_the_search() -> None:
    skill, _, opener = make([hit(f"{DL}/x.pdf")], existing=set())
    assert skill.execute("abrir_arquivo", file_slot("x"), CTX) == FileGone("x.pdf")
    assert opener.opened == []


def test_newest_download_and_newest_screenshot() -> None:
    hits = [
        hit(f"{DL}/old.zip", datetime(2026, 10, 1)),
        hit(f"{DL}/new.zip", datetime(2026, 10, 16, 9)),
        hit(f"{SHOTS}/Captura.png", datetime(2026, 10, 16, 10)),
    ]
    skill, _, opener = make(hits)
    assert skill.execute("abrir_recente", {}, CTX) == FileOpened("new.zip")
    shots = folder_slot("Capturas de Tela")
    assert skill.execute("abrir_recente", shots, CTX) == FileOpened("Captura.png")
    assert opener.opened == [f"{DL}/new.zip", f"{SHOTS}/Captura.png"]


def test_listing_todays_downloads() -> None:
    hits = [
        hit(f"{DL}/a.pdf", datetime(2026, 10, 16, 9)),
        hit(f"{DL}/b.zip", datetime(2026, 10, 16, 11)),
        hit(f"{DL}/ontem.zip", datetime(2026, 10, 15, 23)),
    ]
    skill, _, _ = make(hits)
    assert skill.execute("listar_recentes", {}, CTX) == RecentFiles(2, ("b.zip", "a.pdf"))


def test_nothing_downloaded_today() -> None:
    skill, _, _ = make([hit(f"{DL}/ontem.zip", datetime(2026, 10, 15, 23))])
    assert skill.execute("listar_recentes", {}, CTX) == NothingRecent()
    skill, _, _ = make([])
    assert skill.execute("abrir_recente", {}, CTX) == NothingRecent()
