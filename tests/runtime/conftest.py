import pytest

from support.harness import Make, build_harness


@pytest.fixture
def make() -> Make:
    return build_harness
