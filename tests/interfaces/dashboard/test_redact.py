import pytest

from sazed.interfaces.dashboard.redact import REDACTED, config_rows, is_sensitive, redact


@pytest.mark.parametrize(
    ("name", "sensitive"),
    [
        ("api_key", True),
        ("KEY", True),
        ("github_token", True),
        ("Password", True),
        ("client_secret", True),
        ("t_exec", False),
        ("embedder_path", False),
        ("name", False),
    ],
)
def test_is_sensitive(name: str, sensitive: bool) -> None:
    assert is_sensitive(name) is sensitive


def test_redact_is_recursive_and_keeps_other_values() -> None:
    data = {
        "user": {"name": "Artur"},
        "service": {"api_key": "abc", "nested": [{"token": "t"}, {"ok": 1}]},
        "password": {"whole": "section"},
        "nlu": {"t_exec": 0.94},
    }
    assert redact(data) == {
        "user": {"name": "Artur"},
        "service": {"api_key": REDACTED, "nested": [{"token": REDACTED}, {"ok": 1}]},
        "password": REDACTED,
        "nlu": {"t_exec": 0.94},
    }


def test_redacted_value_never_contains_the_secret() -> None:
    assert "abc" not in str(redact({"secret": "abc"}))


def test_config_rows_flatten_and_mark_the_origin() -> None:
    effective = {
        "user": {"name": "Artur"},
        "nlu": {"t_exec": 0.9, "g_min": 0.01},
        "aliases": {},
        "service": {"token": "xyz"},
    }
    raw = {"nlu": {"t_exec": 0.9}, "service": {"token": "xyz"}}
    rows = config_rows(effective, raw)
    assert [(r.key, r.value, r.origin) for r in rows] == [
        ("user.name", "Artur", "padrão"),
        ("nlu.t_exec", 0.9, "arquivo"),
        ("nlu.g_min", 0.01, "padrão"),
        ("aliases", {}, "padrão"),
        ("service.token", REDACTED, "arquivo"),
    ]


def test_config_rows_redact_by_any_path_segment() -> None:
    rows = config_rows({"secrets": {"plain": "x"}}, {})
    assert [(r.key, r.value) for r in rows] == [("secrets", REDACTED)]
