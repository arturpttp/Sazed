from collections.abc import Sequence
from typing import Protocol

import numpy as np
import numpy.typing as npt


class Embedder(Protocol):
    """Turns sentences into L2-normalised float32 rows of length `dim`."""

    @property
    def dim(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> npt.NDArray[np.float32]: ...
