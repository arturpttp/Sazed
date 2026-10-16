from pathlib import Path

from sazed.interfaces.dashboard.api import DashboardApi
from support.dashboard import ENDPOINTS, build_api


def test_build_api_seeds_two_episodes_and_redacts_the_test_secret(tmp_path: Path) -> None:
    api = build_api(tmp_path)
    status, payload = api.handle("/api/episodes", {})
    assert status == 200 and payload["total"] == 2
    _, caps = api.handle("/api/capabilities", {})
    assert "sk-SEGREDO" not in str(caps)


def test_build_api_without_a_database(tmp_path: Path) -> None:
    api = build_api(tmp_path, with_db=False)
    assert api.handle("/api/episodes", {})[1]["available"] is False
    assert not (tmp_path / "data" / "coppermind.db").exists()


def test_endpoints_are_every_get_route() -> None:
    assert sorted(ENDPOINTS) == sorted(DashboardApi.ROUTES)
