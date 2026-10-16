from dataclasses import replace
from datetime import datetime

import pytest

from sazed.skills.pc.files import (
    KIND_EXTENSIONS,
    KIND_PHRASES,
    PROGRAM_EXTENSIONS,
    FileHit,
    escape_sql_like,
    file_label,
    is_exact,
    is_program,
    newest_sql,
    search_sql,
)


@pytest.mark.parametrize("ext", sorted(PROGRAM_EXTENSIONS))
def test_every_program_extension_is_a_program_in_any_case(ext: str) -> None:
    assert is_program(f"C:/x/setup{ext}")
    assert is_program(f"C:/x/SETUP{ext.upper()}")


@pytest.mark.parametrize("path", ["C:/x/a.pdf", "C:/x/a.xlsx", "C:/x/a", "C:/x/a.exe.txt"])
def test_documents_are_not_programs(path: str) -> None:
    assert not is_program(path)


def test_the_program_list_covers_the_spec() -> None:
    spec = ".exe .com .bat .cmd .ps1 .psm1 .vbs .vbe .js .jse .wsf .wsh .msi .msp .scr .pif .lnk"
    spec += " .url .hta .cpl .jar .reg .appref-ms"
    assert set(spec.split()) == PROGRAM_EXTENSIONS


def test_no_kind_lists_a_program_extension() -> None:
    assert not {e for exts in KIND_EXTENSIONS.values() for e in exts} & PROGRAM_EXTENSIONS


def test_every_kind_has_a_phrase() -> None:
    assert set(KIND_PHRASES) == set(KIND_EXTENSIONS) | {None}


@pytest.mark.parametrize(
    ("word", "escaped"),
    [
        ("gastos", "gastos"),
        ("d'água", "d''água"),
        ("100%", "100[%]"),
        ("a_b", "a[_]b"),
        ("[x]", "[[]x]"),
    ],
)
def test_like_escaping(word: str, escaped: str) -> None:
    assert escape_sql_like(word) == escaped


def test_search_sql_scopes_words_kinds_and_excludes_folders() -> None:
    sql = search_sql(["gastos", "agua"], [".xlsx", ".csv"], ["C:/Users/A"], 6)
    assert sql == (
        "SELECT TOP 6 System.ItemPathDisplay, System.DateModified FROM SYSTEMINDEX "
        "WHERE (SCOPE='file:C:/Users/A') AND System.Kind <> 'folder' "
        "AND System.FileName LIKE '%gastos%' AND System.FileName LIKE '%agua%' "
        "AND (System.FileExtension = '.xlsx' OR System.FileExtension = '.csv') "
        "ORDER BY System.DateModified DESC"
    )


def test_an_accented_word_also_matches_without_its_accents() -> None:
    sql = search_sql(["relatório"], [], ["C:/U"], 6)
    assert "(System.FileName LIKE '%relatório%' OR System.FileName LIKE '%relatorio%')" in sql


def test_several_scopes_are_alternatives() -> None:
    sql = search_sql(["x"], [], ["C:/U", "D:/Projetos"], 6)
    assert "(SCOPE='file:C:/U' OR SCOPE='file:D:/Projetos')" in sql


@pytest.mark.parametrize("attack", ["x' OR 1=1 --", "a'; DROP TABLE x; --", "%' OR '1'='1"])
def test_an_injection_attempt_stays_inside_the_string(attack: str) -> None:
    sql = search_sql([attack], [], ["C:/U"], 6)
    assert f"LIKE '%{escape_sql_like(attack)}%'" in sql
    assert sql.count("'") % 2 == 0
    assert sql.endswith("ORDER BY System.DateModified DESC")


def test_a_scope_with_a_quote_is_escaped() -> None:
    assert "SCOPE='file:C:/Users/O''Brien'" in search_sql(["x"], [], ["C:/Users/O'Brien"], 6)


def test_newest_sql_limits_to_one_folder_and_a_start() -> None:
    sql = newest_sql("C:/U/Downloads", datetime(2026, 10, 16), 10)
    assert sql == (
        "SELECT TOP 10 System.ItemPathDisplay, System.DateModified FROM SYSTEMINDEX "
        "WHERE DIRECTORY='file:C:/U/Downloads' AND System.Kind <> 'folder' "
        "AND System.DateModified >= '2026-10-16 00:00:00' "
        "ORDER BY System.DateModified DESC"
    )


NOW = datetime(2026, 10, 16, 15, 0)
HIT = FileHit("C:/U/Documents/r.docx", "r.docx", "Documents", datetime(2026, 10, 16, 14, 2))


def test_labels_say_today_with_the_time() -> None:
    assert file_label(HIT, NOW) == "r.docx (Documents, hoje 14:02)"


def test_labels_say_yesterday() -> None:
    assert file_label(replace(HIT, modified=datetime(2026, 10, 15, 9, 0)), NOW) == (
        "r.docx (Documents, ontem)"
    )


def test_older_labels_give_the_date() -> None:
    assert file_label(replace(HIT, modified=datetime(2026, 10, 12, 9, 0)), NOW) == (
        "r.docx (Documents, 12/10)"
    )
    assert file_label(replace(HIT, modified=datetime(2025, 10, 12, 9, 0)), NOW) == (
        "r.docx (Documents, 12/10/2025)"
    )


def test_exact_ignores_extension_accents_and_case() -> None:
    hit = FileHit("C:/a/Relatório.docx", "Relatório.docx", "a", datetime(2026, 1, 1))
    assert is_exact(hit, "relatorio")
    assert is_exact(hit, "RELATÓRIO")
    assert not is_exact(hit, "relat")
