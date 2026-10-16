"""Native load order on the real machine. Run with: uv run pytest -m windows

Found by running the dashboard: loading WinRT (the Store catalog) and *then* importing
onnxruntime crashes the process with an access violation. It runs in a subprocess because a
native crash would take pytest down with it.
"""

import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.windows

SCRIPT = textwrap.dedent(
    """
    from sazed.runtime.editing import real_catalog
    names = [e.name for e in real_catalog().entries()]   # loads WinRT for the Store apps
    import onnxruntime                                     # the model's runtime, afterwards
    print(len(names) > 0, onnxruntime.__version__ != "")
    """
)


def test_catalog_first_then_onnxruntime_does_not_crash() -> None:
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == "True True"
