import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from sazed.adapters.sqlite.coppermind import SqliteCoppermind
from sazed.adapters.sqlite.reader import CoppermindReader, CoppermindUnavailable
from sazed.core.coppermind import Episode, NewAlias, NewExample, Reaction
from sazed.core.types import IntentScore

T0 = datetime(2026, 10, 14, 12, 0)


def _episode(text: str, decision: str, *, at: datetime = T0, outcome: str = "") -> Episode:
    return Episode(
        utterance=text,
        at=at,
        ranking=(IntentScore("abrir_app", 0.95), IntentScore("fechar_app", 0.90)),
        slots={"app": "Google Chrome"},
        decision=decision,
        intent_id="abrir_app" if decision != "NotUnderstood" else None,
        outcome=outcome,
    )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "coppermind.db"
    store = SqliteCoppermind(path)
    store.learn([NewExample("abre o chrome", "abrir_app", b"\x00", "confirmed")], [], T0)
    store.learn([], [NewAlias("app", "zap", "WhatsApp")], datetime(2026, 10, 15, 9, 0))
    store.record_episode(_episode("abre o chrome", "Execute", outcome="AppOpened"))
    second = store.record_episode(_episode("toca uma musica", "NotUnderstood"))
    store.set_reaction(second, Reaction.DENIED)
    store.close()
    return path


def test_reads_episodes_newest_first_with_decoded_fields(db: Path) -> None:
    newest, oldest = CoppermindReader(db).episodes(limit=10)
    assert newest.utterance == "toca uma musica"
    assert (newest.decision, newest.reaction, newest.intent_id) == ("NotUnderstood", "denied", None)
    assert oldest.ranking == [("abrir_app", 0.95), ("fechar_app", 0.90)]
    assert oldest.slots == {"app": "Google Chrome"}
    assert oldest.at == T0.isoformat()
    assert oldest.outcome == "AppOpened"


def test_episodes_filter_by_text_decision_and_intent(db: Path) -> None:
    reader = CoppermindReader(db)
    assert [e.utterance for e in reader.episodes(10, search="CHROME")] == ["abre o chrome"]
    assert [e.utterance for e in reader.episodes(10, decision="NotUnderstood")] == [
        "toca uma musica"
    ]
    assert [e.utterance for e in reader.episodes(10, intent="abrir_app")] == ["abre o chrome"]
    assert reader.count_episodes(decision="Execute") == 1
    assert reader.count_episodes() == 2


def test_episodes_page_with_offset(db: Path) -> None:
    assert [e.utterance for e in CoppermindReader(db).episodes(1, offset=1)] == ["abre o chrome"]


def test_search_treats_like_wildcards_literally(db: Path) -> None:
    assert CoppermindReader(db).episodes(10, search="%") == []
    assert CoppermindReader(db).episodes(10, search="_") == []


def test_examples_and_aliases(db: Path) -> None:
    reader = CoppermindReader(db)
    (example,) = reader.examples()
    assert (example.text, example.intent_id, example.origin) == (
        "abre o chrome",
        "abrir_app",
        "confirmed",
    )
    assert example.created_at == T0.isoformat()
    (alias,) = reader.aliases(search="zap")
    assert (alias.slot, alias.alias, alias.value) == ("app", "zap", "WhatsApp")
    assert reader.aliases(search="nada") == []


def test_learned_dates_cover_both_kinds(db: Path) -> None:
    assert sorted(CoppermindReader(db).learned_dates()) == [
        ("alias", "2026-10-15T09:00:00"),
        ("example", T0.isoformat()),
    ]


def test_episode_summaries_since(db: Path) -> None:
    rows = CoppermindReader(db).episode_summaries()
    assert {(r.decision, r.reaction) for r in rows} == {
        ("Execute", "none"),
        ("NotUnderstood", "denied"),
    }


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "coppermind.db"  # the folder exists, so SQLite could create the file
    with pytest.raises(CoppermindUnavailable):
        CoppermindReader(path).episodes(10)
    assert not path.exists()


def test_missing_data_dir_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "nao-existe" / "coppermind.db"
    with pytest.raises(CoppermindUnavailable):
        CoppermindReader(path).count_episodes()
    assert not path.parent.exists()


def test_connection_is_read_only(db: Path) -> None:
    with (
        CoppermindReader(db).connect() as conn,
        pytest.raises(sqlite3.OperationalError, match="readonly"),
    ):
        conn.execute("DELETE FROM episodes")
    assert CoppermindReader(db).count_episodes() == 2


def test_a_locked_or_corrupt_file_is_a_typed_failure(tmp_path: Path) -> None:
    path = tmp_path / "coppermind.db"
    path.write_bytes(b"isto nao e um banco sqlite" * 100)
    with pytest.raises(CoppermindUnavailable) as caught:
        CoppermindReader(path).episodes(10)
    assert "sqlite" not in str(caught.value).lower()


def test_malformed_json_columns_are_tolerated(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.execute("UPDATE episodes SET ranking = 'xx', slots = '[1]' WHERE id = 1")
    conn.commit()
    conn.close()
    oldest = CoppermindReader(db).episodes(10)[-1]
    assert (oldest.ranking, oldest.slots) == ([], {})
