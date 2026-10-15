from importlib.metadata import version

import sazed


def test_version_matches_installed_metadata() -> None:
    assert sazed.__version__ == version("sazed")
